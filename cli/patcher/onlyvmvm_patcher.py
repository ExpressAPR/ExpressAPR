import pathlib
import shutil
import logging
from shlex import quote
from typing import List

from ..runtime_env import RuntimeEnv
from ..utils import run_cmd
from . import BasePatcher, prioritize_tests, get_class_name_from_fn


class OnlyVmvmPatcher(BasePatcher):
    IGNITER_PATH = pathlib.Path('../expapr-jar')
    COMPILE_TIMEOUT_SEC = 180
    RUN_TEST_TIMEOUT_SEC = 600*4

    def __init__(self, jsonpath, env: RuntimeEnv, eidx: int):
        super().__init__(jsonpath, env, eidx)
        self.JAVAC_PATH = 'javac' #self.env.d4j_root/'major/bin/javac'

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

        self.vmvm_jar_path = (self.IGNITER_PATH/"data/runtime-vendor/vmvm-2.0.0-EXPAPR.jar").resolve()
        self.cp_prepend = (
            str((self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve())
            +':'+str(self.vmvm_jar_path)
            +':'
        )

    def compile_runtime_main(self):
        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'{self.JAVAC_PATH}'
            f' -cp {quote(self.cp_prepend+self.cp_test)}'
            f' -d {quote(str((self.workpath/self.tp_test).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f':{quote(str((self.workpath/self.sp_test).resolve()))}'
            f' -source {self.mk_lang_arg(lang_level)} -target {self.mk_lang_arg(lang_level)}'
            f' {quote(str((self.workpath/self.sp_test/"expressapr/testkit/Main.java").resolve()))}'
        )

        errcode, time_sec, stdout, stderr = run_cmd(javac_cmdline, timeout_sec=self.COMPILE_TIMEOUT_SEC, cwd=str(self.IGNITER_PATH))

        if errcode:
            raise RuntimeError(f'compile main error\n\nerrcode={errcode}\nstdout={stdout}\n\nstderr={stderr}')

    def precompile_code(self):
        ##x https://stackoverflow.com/questions/6623161/javac-option-to-compile-all-java-files-under-a-given-directory-recursively
        logging.info('precompile code')

        succ, _, stdout, stderr = self.env.interface.compile(self.workdir_s, timeout_sec=self.COMPILE_TIMEOUT_SEC)

        if not succ:
            raise RuntimeError(f'precompile failed\n\nstdout={stdout}\n\nstderr={stderr}')

    def run_instrumented(self) -> List[str]: # list of failed tests
        logging.info('run instrumented (this may take a while)')

        cmdline = (
            f'{self.java_env}'
            f' java -ea'
            f' -cp'
            f' {(self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve()}'
            f':{(self.IGNITER_PATH/"data/runtime-vendor/hamcrest-core-1.3.jar").resolve()}'
            f':{self.vmvm_jar_path}'
            f':{self.cp_test}'
            f' -Xbootclasspath/p:{self.vmvm_jar_path}'
            f' -javaagent:{self.vmvm_jar_path}'
            f' expressapr.testkit.Main'
        )
        timeout = self.RUN_TEST_TIMEOUT_SEC

        sh_path = (self.workpath/"_run_onlyvmvm.sh")
        with sh_path.open('w') as f:
            f.write(
                f'#!/bin/bash\n'
                f'cd {self.workpath}\n'
                f'{cmdline}\n'
            )
        sh_path.chmod(0o755)

        errcode, time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec=timeout, cwd=str(self.workpath))

        if errcode or 'RUNTEST DONE! ==' not in stdout:
            logging.error('run instrumented error: %d', errcode)
            logging.error('stderr: %s', stderr)
            logging.error('stdout: %s', stdout)
            raise RuntimeError(f'run instrumented failed: errcode={errcode}')

        trails = [x for x in stdout.rpartition('RUNTEST DONE! ==')[2].splitlines() if x]
        logging.debug(stdout)
        #print(trails)

        return trails

    def install_runtime(self):
        src_path = pathlib.Path('../expapr-jar/onlyvmvm-runtime')
        shutil.copytree(src_path, self.workpath/self.sp_test, dirs_exist_ok=True)

        patched_class_name = get_class_name_from_fn(self.config.filename, self.sp_src)
        test_classes = list(set([clz for clz, mtd, _t in prioritize_tests(
            [(clz, "_method", 0) for clz in self.tests_all],
            self.tests_trigger,
            patched_class_name,
        )]))
        test_str = ','.join([f'{t}.class' for t in test_classes])

        main_path = self.workpath/self.sp_test/'expressapr/testkit/Main.java'
        with main_path.open('r') as f:
            main_src = f.read()
        main_src = main_src.replace('[[[TEST_CLASSES]]]', test_str)
        with main_path.open('w') as f:
            f.write(main_src)

    def main(self) -> List[str]: # list of tests and measured time, `clz::mtd::time`
        self.fixup_if_needed()
        self.precompile_code()
        self.install_runtime()
        self.compile_runtime_main()
        test_measures = self.run_instrumented()

        return test_measures
