import socket
import subprocess
import logging
import json
import threading
from pathlib import Path
from typing import Tuple

from cli.utils import randn, kill_tree

class ServantConnector:
    BANNER = 'SERVANT_RPC_V2'

    def __init__(self, enable_assertion: bool, igniter_path: Path):
        self.enable_assertion = enable_assertion
        self.igniter_path_s = str(igniter_path.resolve())
        self.logger = logging.getLogger('servant')
        self.SHOW_STDOUT = self.logger.getEffectiveLevel()==logging.DEBUG

        self.startup_reqs = []
        self.servant = self._start_servant()

    def _start_servant(self):
        svr = socket.socket()
        svr.bind(('127.0.0.1', 0))
        svr.listen(1)

        ret = {}
        port = svr.getsockname()[1]
        nonce = randn(8)
        ready = threading.Event()

        proc_pid = self._spawn_proc(port, nonce)

        def shutdown():
            self.logger.info('servant shutdown')
            svr.close()
            kill_tree(proc_pid)
            ret['stopped'] = True

        ret = {
            'port': port,

            'rpc': lambda _req, _timeout: ('FAIL', {'error': 'servant not ready'}),
            'shutdown': shutdown,

            'ready': ready,
            'stopped': False,
        }

        def handle_conn(s):
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, True)
            reader = s.makefile('r')

            banner = reader.readline().strip()
            assert banner==self.BANNER, f'banner mismatch: got {banner}'

            nonce = reader.readline().strip()
            assert nonce==nonce, f'nonce mismatch: got {nonce}'

            def rpc(req: dict, timeout: int) -> Tuple[str, dict]:
                s.settimeout(timeout)

                req_line = json.dumps(req)
                assert '\n' not in req_line, 'json should contain line breaks'
                self.logger.debug('rpc sent %s', req_line[:150])

                s.sendall(req_line.encode('utf-8') + b'\n')

                status = reader.readline().strip()
                res_line = reader.readline()
                self.logger.debug('rpc received %s: %s', status, res_line)
                return status, json.loads(res_line)

            ret['rpc'] = rpc

        def daemon():
            self.logger.debug('waiting for connection')
            conn, addr = svr.accept()
            self.logger.debug('accepted connection from %s', addr)

            try:
                handle_conn(conn)
            except Exception as e: # during handshake
                self.logger.exception(e)

                conn.close()
                shutdown()
                ready.set()
            else:
                if self.startup_reqs:
                    self.logger.info('sending startup requests')
                    for req, timeout_s in self.startup_reqs:
                        status, res = ret['rpc'](req, timeout_s)
                        if status=='FAIL':
                            self.logger.error('startup request failed: %s', res)
                            shutdown()

                self.logger.info('set state to ready')

                ready.set()

        threading.Thread(target=daemon, daemon=True).start()

        return ret

    def _spawn_proc(self, port: int, nonce: str) -> int:
        cmdline = (
            f'java'
            f' {"-ea" if self.enable_assertion else ""}'
            f' -cp express-apr.jar'
            f' expressapr.igniter.Servant'
            
            f' {port}'
            f' {nonce}'
        )

        self.logger.debug('spawn servant proc: %s', cmdline)

        proc = subprocess.Popen(
            cmdline, cwd=self.igniter_path_s,
            shell=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE if self.SHOW_STDOUT else subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )

        if self.SHOW_STDOUT:
            def handler():
                for line in proc.stdout:
                    self.logger.debug('STDOUT: %s',line.decode('utf-8').rstrip())
                self.logger.info('STDOUT: (eof)')

            threading.Thread(target=handler, daemon=True).start()

        return proc.pid


    def request(self, req: dict, timeout_s: int) -> Tuple[str, dict]:
        self.servant['ready'].wait()
        if self.servant['stopped']:
            self.servant = self._start_servant()
            raise Exception('servant stopped')

        try:
            return self.servant['rpc'](req, timeout_s)
        except Exception as e:
            self.logger.exception(e)
            self.restart()
            raise

    def request_on_startup(self, req: dict, timeout_s: int) -> Tuple[str, dict]:
        ret = self.request(req, timeout_s)
        self.startup_reqs.append((req, timeout_s))
        return ret

    def shutdown(self):
        if not self.servant['stopped']:
            self.servant['shutdown']()

    def restart(self):
        self.shutdown()
        self.servant = self._start_servant()

    def __del__(self):
        self.shutdown()