from typing import TYPE_CHECKING, List, Optional, Tuple, Dict, Any
from pathlib import Path
import logging
import shutil
from shlex import quote
from xml.etree import ElementTree

from . import Interface, register
from ..utils import run_cmd, check_output, randn

if TYPE_CHECKING:
    from ..runtime_env import RuntimeEnv

@register
class InterfaceMaven(Interface):
    NAME = 'maven'
    _MVN_ARG = (
        ' -Dlicense.skipCheckLicense=true'
        ' -Dmaven.javadoc.skip=true'
        ' -Dmaven.site.skip=true'
        ' -Denforcer.skip=true'
        ' -Dcheckstyle.skip=true'
        ' -Dcobertura.skip=true'
        ' -DskipITs=true'
        ' -Drat.skip=true'
        ' -Dlicense.skip=true'
        ' -Dpmd.skip=true'
        ' -Dfindbugs.skip=true'
        ' -Dgpg.skip=true'
        ' -Dskip.npm=true'
        ' -Dskip.gulp=true'
        ' -Dskip.bower=true'
        ' -Danimal.sniffer.skip=true'
    )

    def __init__(self, env: 'RuntimeEnv'):
        super().__init__(env)

        self._check_env_maven()

    def save_init_data(self) -> Dict[str, Any]:
        all_tests, fail_tests = self._reflect_test_info()
        assert len(fail_tests)>0, 'cannot find failed tests for maven project'
        return {
            'test_cases_failing': fail_tests,
            'test_classes': list(set([t[0] for t in all_tests])),
        }

    def _check_env_maven(self) -> None:
        # check maven version

        maven_ver = check_output(f'mvn -version', 5).partition('\n')[0]
        if 'Maven 3.' not in maven_ver:
            raise RuntimeError('invalid maven version (%s), 3.* required'%maven_ver)

    def _export(self, workdir: str, propname: str, pre_cmd: str = '') -> Optional[str]:
        assert Path(workdir).exists()

        resfile = Path(workdir)/f'export_{randn(6)}.txt'

        check_output((
            f'mvn'
            f' {pre_cmd}'
            f' org.apache.maven.plugins:maven-help-plugin:3.1.0:evaluate'
            f' -Dexpression={quote(propname)}'
            f' -Doutput={resfile}'
            f' -DskipTests {self._MVN_ARG}'
        ), cwd=str(workdir), timeout_sec=90)
        assert resfile.exists(), 'cannot export '+propname

        with resfile.open() as f:
            ret = f.read()

        if ret=='null object or invalid expression':
            return None
        return ret

    def _test(self, workdir: str, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, List[Tuple[str, str]], List[Tuple[str, str]]]:
        assert Path(workdir).exists()
        if test:
            assert '::' in test  # test_class::test_method
            test = test.replace('::', '#')

        report_path = Path(workdir)/'target/surefire-reports'
        if report_path.exists():
            shutil.rmtree(report_path)

        errcode, tsec, stdout, stderr = run_cmd((
            'mvn'
            ' test'
            ' -Dmaven.test.failure.ignore=true'
            f'{" -Dtest="+quote(test) if test else ""}'
            f' {self._MVN_ARG}'
        ), timeout_sec, workdir)
        assert errcode==0, f'errcode={errcode}\n\n{stdout}\n\n{stderr}'
        assert report_path.is_dir(), f'errcode={errcode}\n\n{stdout}\n\n{stderr}'

        all_tests = set()
        fail_tests = set()
        for p in report_path.glob('TEST-*.xml'):
            xml = ElementTree.parse(p).getroot()
            for test in xml.findall('./testcase'):
                all_tests.add((test.get('classname'), test.get('name')))
            for fail_test in xml.findall('./testcase/error/..'):
                fail_tests.add((fail_test.get('classname'), fail_test.get('name')))
            for fail_test in xml.findall('./testcase/failure/..'):
                fail_tests.add((fail_test.get('classname'), fail_test.get('name')))

        return tsec, list(all_tests), list(fail_tests)

    def _reflect_test_info(self) -> Tuple[List[Tuple[str, str]], List[Tuple[str, str]]]:
        logging.info('reflecting test info for maven project')

        projpath = self.env.workpath / 'tmp-maven-reflect'
        if projpath.exists():
            shutil.rmtree(projpath)

        self.checkout(str(projpath))

        _tsec, all_tests, fail_tests = self._test(str(projpath), timeout_sec=600)

        shutil.rmtree(projpath)
        return all_tests, fail_tests

    def checkout(self, workdir: str) -> None:
        src = Path(self.env.bug_name)
        dst = Path(workdir)

        assert src.is_dir()
        assert not dst.exists()
        shutil.copytree(src, dst, ignore_dangling_symlinks=True)

        # setup git for workdir

        if not (dst/'.git').exists():
            check_output('git init', 30, workdir)

        check_output('git add .', 30, workdir)
        check_output('git commit --allow-empty -m "expapr init"', 30, workdir)

    def compile(self, workdir: str, timeout_sec: Optional[float] = None) -> Tuple[bool, float, str, str]:
        assert Path(workdir).exists()

        errcode, tsec, stdout, stderr = run_cmd(f'mvn test-compile -DskipTests {self._MVN_ARG}', timeout_sec, workdir)
        return errcode==0, tsec, stdout, stderr

    def test(self, workdir: str, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, List[Tuple[str, str]]]:
        tsec, _all_tests, fail_tests = self._test(workdir, test, timeout_sec)
        return tsec, fail_tests

    @staticmethod
    def _fail(workdir: str):
        raise RuntimeError(f'maven failure for {workdir}')

    @staticmethod
    def _make_relative(base: str, target: str):
        base = Path(base)
        target = Path(target)
        return str(target.relative_to(base))

    def export_cp_compile(self, workdir: str) -> str:
        return self._export(workdir, 'expapr.export_tmp', 'dependency:build-classpath -DincludeScope=compile -Dmdep.outputProperty=expapr.export_tmp') or self._fail(workdir)

    def export_cp_test(self, workdir: str) -> str:
        cp = self._export(workdir, 'expapr.export_tmp', 'dependency:build-classpath -DincludeScope=test -Dmdep.outputProperty=expapr.export_tmp') or self._fail(workdir)
        tp_src = self._export(workdir, 'project.build.outputDirectory') or self._fail(workdir)
        tp_test = self._export(workdir, 'project.build.testOutputDirectory') or self._fail(workdir)
        return f'{cp}:{tp_src}:{tp_test}'

    def export_lang_level(self, workdir: str) -> int:
        lv = self._export(workdir, 'javac.src.version') or self._export(workdir, 'maven.compiler.source') or '1.8'
        assert lv.startswith('1.'), f'invalid lang level: {lv}'
        assert lv[2:].isdigit(), f'invalid lang level: {lv}'
        return int(lv[2:])

    def export_java_env(self, workdir: str) -> str:
        return ''

    def export_tp_src(self, workdir: str) -> str:
        return self._make_relative(workdir, self._export(workdir, 'project.build.outputDirectory') or self._fail(workdir))

    def export_tp_test(self, workdir: str) -> str:
        return self._make_relative(workdir, self._export(workdir, 'project.build.testOutputDirectory') or self._fail(workdir))

    def export_sp_src(self, workdir: str) -> str:
        return self._make_relative(workdir, self._export(workdir, 'project.build.sourceDirectory') or self._fail(workdir))

    def export_sp_test(self, workdir: str) -> str:
        return self._make_relative(workdir, self._export(workdir, 'project.build.testSourceDirectory') or self._fail(workdir))

    def export_tests_all_class(self, workdir: str) -> List[str]:
        ret = self.init_data.get('test_classes', None)
        assert ret is not None, 'test_classes not in init_data'
        return ret

    def export_tests_trigger(self, workdir: str) -> List[str]:
        ret = self.init_data.get('test_cases_failing', None)
        assert ret is not None, 'test_cases_failing not in init_data'
        return [f'{x[0]}::{x[1]}' for x in ret]
