import pathlib
import logging
import time
from shlex import quote
from typing import Tuple, List

from ..runtime_env import RuntimeEnv
from ..utils import run_cmd, randn
from cli.servant_connector import ServantConnector
from . import BasePatcher, prioritize_tests, get_class_name_from_fn


class ExpAprPatcher(BasePatcher):
    ENABLE_ASSERTION = False
    RUNTIME_DEBUG = False
    DUMP_RUNTIME_OUTPUT = False
    TEST_SEL_WHEN_NODEDUP = False
    WRITE_COMPILER_MSG = False

    IGNITER_PATH = pathlib.Path('../expapr-jar')

    COMPILE_MAIN_TIMEOUT_SEC = 180

    INST_TIMEOUT_SEC_BASE = 90
    INST_TIMEOUT_SEC_EACH = 20
    INST_TIMEOUT_SEC_MAX = 1800

    RUN_TEST_TIMEOUT_SEC_BASE = 120
    RUN_TEST_TIMEOUT_SEC_EACH = 300
    RUN_TEST_TIMEOUT_SEC_MAX = 7200

    def __init__(self, jsonpath, env: RuntimeEnv, eidx: int, noprio=False):
        super().__init__(jsonpath, env, eidx)

        self.noprio = noprio

        if self.ENABLE_ASSERTION:
            logging.warning('!! ASSERTION ENABLED: speed is not optimal')
        if self.RUNTIME_DEBUG:
            logging.warning('!! RUNTIME DEBUG ENABLED: speed is not optimal')

        self.cp_compile: str = self.prop("cp_compile")
        self.cp_test: str = self.prop("cp_test")
        self.tp_src: str = self.prop("tp_src")
        self.tp_test: str = self.prop("tp_test")
        self.sp_src: str = self.prop("sp_src")
        self.sp_test: str = self.prop("sp_test")
        self.tests_all: List[str] = self.prop("tests_all_class")
        self.tests_trigger: List[str] = self.prop("tests_trigger")
        self.lang_level: int = self.prop("lang_level")
        self.java_env: str = self.prop("java_env")

        patched_class_name = get_class_name_from_fn(self.config.filename, self.sp_src)
        self.prioritized_applicable_tests = prioritize_tests(
            self.env.applicable_tests,
            [] if self.noprio else self.tests_trigger,
            "" if self.noprio else patched_class_name,
        )

        self.vmvm_jar_path = (self.IGNITER_PATH/"data/runtime-vendor/vmvm-2.0.0-EXPAPR.jar").resolve()
        self.cp_prepend = (
            str((self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve())
            +':'+str(self.vmvm_jar_path)
            +':'
        )

    def compile_runtime_main(self):
        logging.info('compile runtime main')
        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'javac'
            f' -cp {quote(self.cp_prepend+self.cp_test)}'
            f' -d {quote(str((self.workpath/self.tp_test).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f':{quote(str((self.workpath/self.sp_test).resolve()))}'
            f' -source {self.mk_lang_arg(lang_level)} -target {self.mk_lang_arg(lang_level)}'
            f' {quote(str((self.workpath/self.sp_test/"expressapr/testkit/Main.java").resolve()))}'
        )

        timeout = self.COMPILE_MAIN_TIMEOUT_SEC

        errcode, time_sec, stdout, stderr = run_cmd(javac_cmdline, timeout_sec=timeout, cwd=str(self.IGNITER_PATH))

        if errcode:
            logging.error('compile main error: %d', errcode)
            logging.error('stderr: %s', stderr)
            logging.error('stdout: %s', stdout)
            raise RuntimeError('compile main error')

    def _build_compile_target_cmdline(self):
        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'javac'
            f' -J-Duser.language=en'
            f' -nowarn'
            f' -Xmaxerrs 2500'
            f' -cp {quote(self.cp_prepend+self.cp_compile)}'
            f' -d {quote(str((self.workpath/self.tp_src).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f' -source {self.mk_lang_arg(lang_level)} -target {self.mk_lang_arg(lang_level)}'
            f' {quote(str((self.workpath/self.config.filename).resolve()))}'
        )

        return javac_cmdline

    # DEPRECATED! this will fail (OSError: [Errno 7] Argument list too long: '/bin/sh') if there are too many tests
    # use install_instrumentation_servant instead.
    def install_instrumentation_cli(self) -> Tuple[int, str, List[int]]: # (patch count left, succlist, telemetry_cnts)
        logging.info('install instrumentation (cli)')

        tests = [f'{clz}::{mtd}::{timeout}' for t in self.prioritized_applicable_tests for clz, mtd, timeout in [t]]

        cmdline = (
            f'java'
            f' {"-ea" if self.ENABLE_ASSERTION else ""}'
            f' -cp express-apr.jar'
            f' expressapr.igniter.Cli'
            
            f' {self.configpath.resolve()}'  # patches_json_fn
            f' {self.workpath.resolve()}'  # project_root_path
            f' abandoned'  # related_test_classes
            f' {self.sp_src}'  # project_src_path
            f' {self.sp_test}'  # project_test_path
            f' {quote(self._build_compile_target_cmdline())}'  # javac_cmdline
            f' {"dedup-off" if self.env.deduplication["type"]!="sidefx_db" else "dedup-on"}' # dedup_flag
            f' {self.env.deduplication.get("sidefx_db_path", "/dev/null/xxx")}' # sidefx_db_path
            f' {"|".join(tests)}' # all_tests
        )

        timeout = min(self.INST_TIMEOUT_SEC_BASE + self.INST_TIMEOUT_SEC_EACH*len(self.config.patches), self.INST_TIMEOUT_SEC_MAX)

        errcode, time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec=timeout, cwd=str(self.IGNITER_PATH))

        if errcode and 'sidefx db not found!' in stdout:
            raise RuntimeError('sidefx db not found')

        if errcode or 'PREPROCESS DONE! ==' not in stdout:
            logging.error('install instrumentation error: %d', errcode)
            logging.error('stderr: %s', stderr)
            logging.error('stdout: %s', stdout)
            raise RuntimeError('install instrumentation failed')

        trails = stdout.rpartition('PREPROCESS DONE! ==')[2].splitlines()
        logging.debug(stdout)

        patches_left = -1
        for line in trails:
            if line.startswith('patch count left:'):
                patches_left = int(line.partition(':')[2].strip())
        assert patches_left>=0

        succlist_line = None
        for line in trails:
            if line.startswith('patch status:'):
                succlist_line = line.partition(':')[2].strip()
        assert succlist_line is not None

        telemetry_cnts = None
        for line in trails:
            if line.startswith('Telemetry:'):
                telemetry_cnts = [int(x) for x in line.partition(':')[2].strip().split(' ')]
        assert telemetry_cnts is not None

        return patches_left, succlist_line, telemetry_cnts

    def install_instrumentation_servant(self, action: str, connector: ServantConnector) -> Tuple[int, str, List[int]]:  # (patch count left, succlist, telemetry_cnts)
        logging.info('install instrumentation (servant: %s)', action)

        req = {
            'action': action,

            'patches_json_fn': str(self.configpath.resolve()),
            'project_root_path': str(self.workpath.resolve()),
            'project_src_path': self.sp_src,
            'project_test_path': self.sp_test,
            'javac_cmdline': self._build_compile_target_cmdline(),
            'all_tests': [f'{clz}::{mtd}::{timeout}' for t in self.prioritized_applicable_tests for clz, mtd, timeout in [t]],

            'flags': {
                'runtime_debug': self.RUNTIME_DEBUG,
                'test_sel_when_nodedup': self.TEST_SEL_WHEN_NODEDUP,
                'write_compiler_msg': self.WRITE_COMPILER_MSG,
            }
        }

        timeout = min(self.INST_TIMEOUT_SEC_BASE+self.INST_TIMEOUT_SEC_EACH*len(self.config.patches), self.INST_TIMEOUT_SEC_MAX)

        status, res = connector.request(req, timeout)
        if status!='succ':
            raise RuntimeError('install instrumentation failed: %s' % res)

        return res['compiled_patch_count'], res['status_line'], res['telemetry_cnts']

    def precompile_code(self):
        logging.info('precompile code')

        succ, _, stdout, stderr = self.env.interface.compile(self.workdir_s, timeout_sec=self.COMPILE_MAIN_TIMEOUT_SEC)

        if not succ:
            logging.error('precompile failed')
            logging.error('stderr: %s', stderr)
            logging.error('stdout: %s', stdout)
            raise RuntimeError('precompile failed')

    def run_instrumented(self, patchcnt) -> Tuple[str, List[int]]: # succlist, telemetry_cnts
        logging.info('run instrumented')

        cmdline = (
            f'{self.java_env}'
            f' java {"-ea" if self.ENABLE_ASSERTION else ""}'
            f' -cp'
            f' {(self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve()}'
            f':{(self.IGNITER_PATH/"data/runtime-vendor/hamcrest-core-1.3.jar").resolve()}'
            f':{self.vmvm_jar_path}'
            f':{self.cp_test}'
            f' -Xbootclasspath/p:{self.vmvm_jar_path}'
            f' -javaagent:{self.vmvm_jar_path}'
            f' expressapr.testkit.Main'
        )

        timeout = min(self.RUN_TEST_TIMEOUT_SEC_BASE + self.RUN_TEST_TIMEOUT_SEC_EACH*patchcnt, self.RUN_TEST_TIMEOUT_SEC_MAX)
        cwd = str(self.workpath)
        # PROJS_REQUIRES_RUNNING_TEST_FROM_ROOT
        #cwd = str(self.workpath/self.prop("dir.src.tests"))

        sh_path = (self.workpath/"_run_testkit.sh")
        with sh_path.open('w') as f:
            f.write(
                f'#!/bin/bash\n'
                f'# jsonpath: {self.jsonpath_s}\n'
                f'# src: {self.config.filename}\n'
                f'cd {cwd}\n'
                f'{cmdline}\n'
            )
        sh_path.chmod(0o755)

        errcode, time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec=timeout, cwd=cwd)

        if errcode or 'RUNTEST DONE! ==' not in stdout:
            logging.error('run instrumented error: %d', errcode)
            logging.error('stderr: %s', stderr)
            logging.error('stdout: %s', stdout)

            serial = None
            if self.DUMP_RUNTIME_OUTPUT:
                serial = randn(8)
                p = pathlib.Path('_runtime_dump') / serial
                p.mkdir(parents=True, exist_ok=True)
                with (p/'stdout.txt').open('w') as f:
                    f.write(stdout)
                with (p/'stderr.txt').open('w') as f:
                    f.write(stderr)
                with (p/'jsonpath.txt').open('w') as f:
                    f.write(self.jsonpath_s)

            if serial is None:
                raise RuntimeError(f'run instrumented failed: errcode={errcode} time={time_sec}')
            else:
                raise RuntimeError(f'run instrumented failed (output dumped): errcode={errcode} time={time_sec} serial={serial}')

        trails = stdout.rpartition('RUNTEST DONE! ==')[2].splitlines()
        logging.debug('run instrumented STDOUT: %s', stdout)
        logging.debug('run instrumented STDERR: %s', stderr)
        #logging.debug('run instrumented: %s', trails)

        succlist_line = None
        for line in trails:
            if line.startswith('patch status:'):
                succlist_line = line.partition(':')[2].strip()
        assert succlist_line is not None

        telemetry_cnts = None
        for line in trails:
            if line.startswith('Telemetry:'):
                telemetry_cnts = [int(x) for x in line.partition(':')[2].strip().split(' ')]
        assert telemetry_cnts is not None

        return succlist_line, telemetry_cnts

    @staticmethod
    def fuse_succlist(compile_list, run_list):
        assert compile_list.count('?')==len(run_list), f'succlist length mismatch: c=[{compile_list}] r=[{run_list}]'
        succlist = list(compile_list)

        idx = 0
        for c in run_list:
            while succlist[idx]!='?':
                idx += 1
            succlist[idx] = c

        return ''.join(succlist)

    def main(self, servant: ServantConnector): # patchcnt, t_install, t_run, succlist, inst_telemetry_cnts, run_telemetry_cnts
        self.fixup_if_needed()

        # cached by init process
        #self.precompile_code()

        t1 = time.time()
        patchcnt, succlist, inst_telemetry_cnts = self.install_instrumentation_servant('run', servant)
        t2 = time.time()

        runtime_succlist = ''
        run_telemetry_cnts = None

        if patchcnt!=0:
            runtime_succlist, run_telemetry_cnts = self.run_instrumented(patchcnt)

        t3 = time.time()

        succlist = self.fuse_succlist(succlist, runtime_succlist)

        return patchcnt, t2-t1, t3-t2, succlist, inst_telemetry_cnts, run_telemetry_cnts