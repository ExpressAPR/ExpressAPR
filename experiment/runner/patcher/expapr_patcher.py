import io
import pathlib
import shutil
import time
from shlex import quote
from xml.etree import ElementTree as ET
from typing import Tuple, List

import reporter as rp
import d4j
from utils import run_cmd
from patcher import BasePatcher, VERBOSE


PROJS_REQUIRES_RUNNING_TEST_FROM_ROOT = {
    ('Time', 4), ('Time', 7), ('Time', 15),
    ('Lang', 7), ('Lang', 16),
}


def common_pfx_len(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))


def prioritize_tests(tests_all_s, tests_trigger_s, patched_class_name):
    def filter_test_name(ts):
        # `$`: sometimes we get com.google.javascript.jscomp.SpecializeModuleTest$SpecializeModuleSpecializationStateTest
        return [t for t in ts if t and ('$' not in t) and ('.enum.' not in t)]

    def package_key(t):
        return common_pfx_len(patched_class_name, t.replace('Test', ''))

    tests = sorted(filter_test_name(tests_all_s.splitlines()), key=package_key, reverse=True)
    tests_trigger = filter_test_name(list(set([x.partition('::')[0] for x in tests_trigger_s.splitlines()])))

    return tests_trigger + [x for x in tests if x not in tests_trigger]


def get_class_name_from_fn(java_fn, root_fn):
    # e.g. java_fn = 'source/org/jfree/chart/renderer/category/AbstractCategoryItemRenderer.java'
    #      root_fn = 'source'
    if not java_fn.startswith(root_fn) or not java_fn.endswith('.java'):
        return ''
    java_fn = java_fn[len(root_fn):-5]
    if java_fn.startswith('/'):
        java_fn = java_fn[1:]

    return java_fn.replace('/', '.')


class ExpAprPatcher(BasePatcher):
    ENABLE_ASSERTION = False

    IGNITER_PATH = pathlib.Path('../expapr-jar')

    COMPILE_MAIN_TIMEOUT_SEC = 180

    INST_TIMEOUT_SEC_BASE = 90
    INST_TIMEOUT_SEC_EACH = 20
    INST_TIMEOUT_SEC_MAX = 1800

    RUN_TEST_TIMEOUT_SEC_BASE = 120
    RUN_TEST_TIMEOUT_SEC_EACH = 300
    RUN_TEST_TIMEOUT_SEC_MAX = 7200

    def __init__(self, jsonpath, apr_name, nodedup=False, noprio=False):
        super().__init__(jsonpath, checkout=False)

        self.D4J_PATH = pathlib.Path(d4j.get_d4j_path())
        self.JAVAC_PATH = self.D4J_PATH/'major/bin/javac'
        self.SIDEFX_DB_PATH = self.IGNITER_PATH/'data/sidefx_db'/apr_name/self.config.project.title()/f'{self.config.project.title()}{self.config.version}.csv'

        self.nodedup = nodedup
        self.noprio = noprio

        if self.ENABLE_ASSERTION:
            print('!! ASSERTION ENABLED: speed is not optimal')

        if not nodedup and not self.SIDEFX_DB_PATH.exists():
            raise RuntimeError('sidefx db not found')

        if not self.workpath.exists():
            self.checkout()

        rp.testkit_reporter.attach('workdir', self.workdir_s)

        self.global_xml_file = self.backup_global_xml()

        print('- getting d4j props')

        self.cp_compile = self.prop("cp.compile")
        self.cp_test = self.prop("cp.test") # "Classpath to compile and run the developer-written tests"
        self.tp_src = self.prop("dir.bin.classes")
        self.tp_test = self.prop("dir.bin.tests")
        self.sp_src = self.prop("dir.src.classes")
        self.sp_test = self.prop("dir.src.tests")
        self.tests_all = self.prop("tests.all")
        self.tests_trigger = self.prop("tests.trigger")

        self.cp_prepend = (
            str((self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve())
            +':'+str((self.IGNITER_PATH/"data/runtime-vendor/vmvm-2.0.0-EXPAPR.jar").resolve())
            +':'
        )
        self.lang_level = self.get_language_level()
        rp.testkit_reporter.attach('language_level', self.lang_level)

    def compile_runtime_main(self):
        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'{self.JAVAC_PATH}'
            f' -cp {quote(self.cp_prepend+self.cp_test)}'
            f' -d {quote(str((self.workpath/self.tp_test).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_test).resolve()))}'
            f' -source 1.{lang_level} -target 1.{lang_level}'
            f' {quote(str((self.workpath/self.sp_test/"expressapr/testkit/Main.java").resolve()))}'
        )
        rp.testkit_reporter.attach('compilemain_javac_cmdline', javac_cmdline)

        timeout = self.COMPILE_MAIN_TIMEOUT_SEC

        errcode, time_sec, stdout, stderr = run_cmd(javac_cmdline, timeout_sec=timeout, cwd=str(self.IGNITER_PATH))
        rp.testkit_reporter.attach('compilemain_errcode', errcode)
        rp.testkit_reporter.attach('compilemain_stdout', stdout)
        rp.testkit_reporter.attach('compilemain_stderr', stderr)

        if errcode:
            print('COMPILE MAIN ERROR', errcode)
            print('stderr <<< %s >>>'%stderr)
            print('stdout <<< %s >>>'%stdout)
            1/0

    def install_instrumentation(self) -> Tuple[int, str, List[int]]: # (patch count left, succlist, telemetry_cnts)
        if VERBOSE:
            print('install instrumentation')

        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'{self.JAVAC_PATH}'
            f' -cp {quote(self.cp_prepend+self.cp_compile)}'
            f' -d {quote(str((self.workpath/self.tp_src).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f' -source 1.{lang_level} -target 1.{lang_level}'
            f' {quote(str((self.workpath/self.config.filename).resolve()))}'
        )
        rp.testkit_reporter.attach('instrument_javac_cmdline', javac_cmdline)

        triggering_tests = self.tests_trigger.strip().replace('\n', '|')
        patched_class_name = get_class_name_from_fn(self.config.filename, self.sp_src)

        cmdline = (
            f'java {"-ea" if self.ENABLE_ASSERTION else ""} -jar express-apr.jar'
            f' {self.configpath.resolve()}'  # patches_json_fn
            f' {self.workpath.resolve()}'  # project_root_path
            f' {quote("|".join(prioritize_tests(self.tests_all, "" if self.noprio else self.tests_trigger, "" if self.noprio else patched_class_name)))}'  # related_test_classes
            f' {self.sp_src}'  # project_src_path
            f' {self.sp_test}'  # project_test_path
            f' {quote(javac_cmdline)}'  # javac_cmdline
            f' {"dedup-off" if self.nodedup else "dedup-on"}' # dedup_flag
            f' {self.SIDEFX_DB_PATH.resolve()}' # sidefx_db_path
            f' {quote("" if self.noprio else triggering_tests)}' # triggering_tests
        )
        rp.testkit_reporter.attach('instrument_cmdline', cmdline)
        if VERBOSE:
            print('> instrument cmdline:', cmdline)

        timeout = min(self.INST_TIMEOUT_SEC_BASE + self.INST_TIMEOUT_SEC_EACH*len(self.config.patches), self.INST_TIMEOUT_SEC_MAX)

        errcode, time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec=timeout, cwd=str(self.IGNITER_PATH))
        rp.testkit_reporter.attach('instrument_errcode', errcode)
        rp.testkit_reporter.attach('instrument_stdout', stdout)
        rp.testkit_reporter.attach('instrument_stderr', stderr)
        rp.testkit_reporter.attach_fn('instrument_compile_log_succ', str(self.IGNITER_PATH/'compile-succ.txt'))
        rp.testkit_reporter.attach_fn('instrument_compile_log_error', str(self.IGNITER_PATH/'compile-error.txt'))
        rp.testkit_reporter.attach_fn('patched_file', self.workdir_s+'/'+self.config.filename)

        if errcode and 'sidefx db not found!' in stdout:
            raise RuntimeError('sidefx db not found')

        if errcode or 'PREPROCESS DONE! ==' not in stdout:
            print('INSTALL INSTRUMENTATION ERROR', errcode)
            print('stderr <<< %s >>>'%stderr)
            print('stdout <<< %s >>>'%stdout)
            1/0

        if VERBOSE:
            print(' - install stdout:')
            print(stdout)
            print(stderr)

        trails = stdout.rpartition('PREPROCESS DONE! ==')[2].splitlines()
        print(trails)

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

    def precompile_code(self):
        if VERBOSE:
            print('compile')

        succ, _, stdout, stderr = d4j.compile_verbose(self.workdir_s, timeout_sec=self.COMPILE_MAIN_TIMEOUT_SEC)
        rp.testkit_reporter.attach('precompile_stdout', stdout)
        rp.testkit_reporter.attach('precompile_stderr', stderr)

        if not succ:
            print(' - compile failed')
            raise RuntimeError('compile failed, \nSTDOUT = {\n'+stdout+'\n}\nSTDERR = {\n'+stderr+'\n}')

    def _modify_build_xml(self, xmlpath):
        # https://maven.apache.org/plugins/maven-compiler-plugin/examples/set-compiler-source-and-target.html

        #print(' - modify', xmlpath)
        rp.testkit_reporter.attach('modified_build_xml', str(xmlpath))

        with xmlpath.open('r') as f:
            content = f.read()

        document = ET.ElementTree()
        document.parse(io.StringIO(content))

        for target in document.findall('.//target/javac/..'):
            for javac in target.findall('./javac'):
                # increase java version to something that support generics, asserts, boxing/unboxing, etc.
                if self.lang_level<5:
                    print(' - override javac version')
                    javac.set('source', '1.5')
                    javac.set('target', '1.5')

                # inject classpath for testkit
                for cp_ref in javac.findall('./classpath'):
                    javac.remove(cp_ref)

                cp_elem = ET.Element('classpath')
                if target.get('name')=='compile':
                    cp_elem.append(ET.Element('pathelement', {'path': self.cp_prepend + self.cp_compile}))
                else:
                    cp_elem.append(ET.Element('pathelement', {'path': self.cp_prepend + self.cp_test}))
                javac.append(cp_elem)

                rp.testkit_reporter.attach('modified_javac', str(xmlpath))

        with xmlpath.open('wb') as f:
            document.write(f)

    def backup_global_xml(self):
        global_xml_file = self.D4J_PATH / (
            'framework/projects/{proj}/{proj}.build.xml'.replace('{proj}', self.config.project.title())
        )
        global_bkp_file = pathlib.Path(str(global_xml_file)+'.orig')
        assert global_xml_file.exists()

        if global_bkp_file.exists():
            print('- restore global xml')
            shutil.copy(global_bkp_file, global_xml_file)
        else:
            print('- backup global xml')
            shutil.copy(global_xml_file, global_bkp_file)

        return global_xml_file

    def patch_all_build_xml(self):
        if VERBOSE:
            print('patch all build xml')

        #xxx
        self._modify_build_xml(self.global_xml_file)

        # elf._tamper_d4j_build_xml()

        for p in self.workpath.glob('*.xml'):
            self._modify_build_xml(p)
        for p in self.workpath.glob('ant/*.xml'):
            self._modify_build_xml(p)

    def fixup_if_needed(self):
        if self.config.project.lower()=='lang' and self.config.version in [51, 55, 57, 59]:
            # package name `enum`
            assert (self.workpath/'src/test/org/apache/commons/lang/enums').is_dir()
            assert (self.workpath/'src/java/org/apache/commons/lang/enums').is_dir()
            shutil.rmtree(self.workpath/'src/test/org/apache/commons/lang/enum')
            shutil.rmtree(self.workpath/'src/java/org/apache/commons/lang/enum')
            for p in self.workpath.glob('**/*.java'):
                with p.open('rb') as f:
                    src = f.read()
                src = src\
                    .replace(b'org.apache.commons.lang.enum.', b'org.apache.commons.lang.enums.')\
                    .replace(b'org.apache.commons.lang.enum;', b'org.apache.commons.lang.enums;')
                with p.open('wb') as f:
                    f.write(src)

        if self.config.project.lower()=='mockito':
            # does not compile because of faulty class path
            if self.config.version==29:
                self.cp_compile = (
                    '{BASE}/lib/repackaged/cglib-and-asm-1.0.jar'
                    ':{BASE}/lib/compile/com.springsource.org.junit-4.5.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.hamcrest.core-1.1.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.objenesis-1.0.0.jar'
                    ':{BASE}/target/classes'
                ).replace('{BASE}', str(self.workpath.resolve()))
                self.cp_test = (
                    '{BASE}/lib/repackaged/cglib-and-asm-1.0.jar'
                    ':{BASE}/lib/compile/com.springsource.org.junit-4.5.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.hamcrest.core-1.1.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.objenesis-1.0.0.jar'
                    ':{BASE}/lib/test/powermock-reflect-1.2.5.jar'
                    ':{BASE}/lib/test/fest-assert-1.3.jar'
                    ':{BASE}/lib/test/fest-util-1.1.4.jar'
                    ':{BASE}/target/test-classes'
                    ':{BASE}/target/classes'
                ).replace('{BASE}', str(self.workpath.resolve()))
            elif self.config.version==38:
                self.cp_compile = (
                    '{BASE}/lib/repackaged/cglib-and-asm-1.0.jar'
                    ':{BASE}/lib/compile/com.springsource.org.junit-4.5.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.hamcrest.core-1.1.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.objenesis-1.0.0.jar'
                    ':{BASE}/target/classes'
                ).replace('{BASE}', str(self.workpath.resolve()))
                self.cp_test = (
                    '{BASE}/lib/repackaged/cglib-and-asm-1.0.jar'
                    ':{BASE}/lib/compile/com.springsource.org.junit-4.5.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.hamcrest.core-1.1.0.jar'
                    ':{BASE}/lib/run/com.springsource.org.objenesis-1.0.0.jar'
                    ':{BASE}/lib/test/powermock-reflect-1.2.5.jar'
                    ':{BASE}/target/test-classes'
                    ':{BASE}/target/classes'
                ).replace('{BASE}', str(self.workpath.resolve()))


    def run_instrumented(self, patchcnt) -> Tuple[str, List[int]]: # succlist, telemetry_cnts
        if VERBOSE:
            print('run')

        VMVM_JAR = (self.IGNITER_PATH/"data/runtime-vendor/vmvm-2.0.0-EXPAPR.jar").resolve()

        cmdline = (
            f'java {"-ea" if self.ENABLE_ASSERTION else ""}'
            f' -cp'
            f' {(self.IGNITER_PATH/"data/runtime-vendor/junit-4.12.jar").resolve()}'
            f':{(self.IGNITER_PATH/"data/runtime-vendor/hamcrest-core-1.3.jar").resolve()}'
            f':{VMVM_JAR}'
            f':{self.cp_test}'
            f' -Xbootclasspath/p:{VMVM_JAR}'
            f' -javaagent:{VMVM_JAR}'
            f' expressapr.testkit.Main'
        )
        rp.testkit_reporter.attach('run_cmdline', cmdline)
        if VERBOSE:
            print('> run cmdline:', cmdline)

        timeout = min(self.RUN_TEST_TIMEOUT_SEC_BASE + self.RUN_TEST_TIMEOUT_SEC_EACH*patchcnt, self.RUN_TEST_TIMEOUT_SEC_MAX)
        if (self.config.project, self.config.version) in PROJS_REQUIRES_RUNNING_TEST_FROM_ROOT:
            cwd = str(self.workpath)
        else:
            cwd = str(self.workpath/self.prop("dir.src.tests"))

        sh_path = (self.workpath/"_run_testkit.sh")
        with sh_path.open('w') as f:
            f.write(f'#!/bin/bash\ncd {cwd}\n{cmdline}\n')
        sh_path.chmod(0o755)

        errcode, time_sec, stdout, stderr = run_cmd(cmdline, timeout_sec=timeout, cwd=cwd)
        rp.testkit_reporter.attach('run_errcode', errcode)
        rp.testkit_reporter.attach('run_stdout', stdout)
        rp.testkit_reporter.attach('run_stderr', stderr)

        if errcode or 'RUNTEST DONE! ==' not in stdout:
            print('RUN INSTRUMENTATION ERROR', errcode)
            print('stderr <<< %s >>>'%stderr)
            print('stdout <<< %s >>>'%stdout)
            raise RuntimeError('compile failed, \nSTDOUT = {\n'+stdout+'\n}\nSTDERR = {\n'+stderr+'\n}')

        trails = stdout.rpartition('RUNTEST DONE! ==')[2].splitlines()
        print(trails)

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

    def main(self): # patchcnt, t_install, t_compile, t_run, succlist, inst_telemetry_cnts, run_telemetry_cnts
        if VERBOSE:
            print('main')

        rp.testkit_reporter.attach('unpatched_fn', self.config.filename)
        rp.testkit_reporter.attach_fn('unpatched_file', self.workdir_s+'/'+self.config.filename)

        self.fixup_if_needed()

        rp.testkit_reporter.set_step('patch_xml')
        self.patch_all_build_xml()

        # xxx: for testing
        rp.testkit_reporter.set_step('pre_compile')
        self.precompile_code()

        rp.testkit_reporter.set_step('instrumentation')
        t1 = time.time()
        patchcnt, succlist, inst_telemetry_cnts = self.install_instrumentation()
        t2 = time.time()

        rp.testkit_reporter.attach_fn('patched_file', self.workdir_s+'/'+self.config.filename)
        rp.testkit_reporter.attach('patchcnt', patchcnt)

        t3 = time.time()
        runtime_succlist = ''
        run_telemetry_cnts = None

        if patchcnt!=0:
            rp.testkit_reporter.set_step('compilemain')
            self.compile_runtime_main()

            t3 = time.time()

            rp.testkit_reporter.set_step('run')
            runtime_succlist, run_telemetry_cnts = self.run_instrumented(patchcnt)

        t4 = time.time()

        self.backup_global_xml() # restore build xml for good

        succlist = self.fuse_succlist(succlist, runtime_succlist)

        return patchcnt, t2-t1, t3-t2, t4-t3, succlist, inst_telemetry_cnts, run_telemetry_cnts
