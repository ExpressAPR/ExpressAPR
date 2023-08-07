import random
import logging
import subprocess
import time
import shutil
import os
from pathlib import Path
from typing import Optional, Tuple
import psutil

log = logging.getLogger('utils')

def kill_tree(parent_pid): # https://psutil.readthedocs.io/en/latest/#kill-process-tree
    try:
        p = psutil.Process(parent_pid)
    except psutil.NoSuchProcess:
        return

    ps = p.children(recursive=True)
    ps.append(p)
    log.debug('kill_tree: pid %s (%d processes)', parent_pid, len(ps))

    for proc in ps:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass

    # release subprocess resources
    for proc in ps:
        try:
            os.waitpid(proc.pid, 0)
        except OSError:
            pass

def run_cmd(cmdline: str, timeout_sec: Optional[float] = None, cwd: Optional[str] = None) -> Tuple[int, float, str, str]:  # errcode, time_sec, stdout, stderr
    log.debug('run_cmd: %s', cmdline)

    p = subprocess.Popen(
        cmdline, cwd=cwd,
        shell=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    t1 = time.time()

    try:
        pout, perr = p.communicate(timeout=timeout_sec)
        errcode = p.wait()
    except subprocess.TimeoutExpired:
        log.warning('run_cmd TIMEOUT: %s', cmdline)
        kill_tree(p.pid)
        pout, perr = p.communicate(timeout=timeout_sec)
        errcode = -1337

    t2 = time.time()

    if errcode:
        log.warning('run_cmd RETURNED %d: %s (cwd = %s)', errcode, cmdline, cwd)
        log.debug('run_cmd: stdout is %r', pout.decode('utf-8', 'ignore'))
        log.debug('run_cmd: stderr is %r', perr.decode('utf-8', 'ignore'))

    return errcode, t2-t1, pout.decode('utf-8', 'replace'), perr.decode('utf-8', 'replace')

def check_output(cmdline: str, timeout_sec: Optional[float] = None, cwd: Optional[str] = None, expect_errcode: int = 0, check_stderr: bool = False) -> str:
    if expect_errcode!=0:
        log.setLevel(logging.ERROR)

    errcode, _time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec, cwd)

    if expect_errcode!=0:
        log.setLevel(logging.NOTSET)

    if errcode!=expect_errcode:
        raise RuntimeError(f'check_output: returned {errcode} (expected {expect_errcode})\ncmdline: {cmdline!r}\n\ncwd: {cwd}\n\nstdout:\n{stdout}\n\nstderr:\n{stderr}')
    return stderr if check_stderr else stdout

def randn(n):
    ALPHABET = 'qwertyuiopasdfghjklzxcvbnm'
    return ''.join([random.choice(ALPHABET) for _ in range(n)])

def copy_tree_retry(src: Path, dst: Path):
    # shutil.copytree occasionally fails with "[Errno 2] No such file or directory". idk why but this is a workaround.
    for retries_left in range(2, -1, -1):
        try:
            shutil.copytree(src, dst)
            break
        except shutil.Error as e:
            logging.warning(f'copytree failed, will retry {retries_left} times: {e}')
            time.sleep(.2)
            if dst.is_dir():
                shutil.rmtree(dst)
            time.sleep(.2)
    else:  # all failed
        raise RuntimeError(f'cannot copy tree from {src!r} to {dst!r}')