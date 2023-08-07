from typing import List, Optional, Tuple, Dict, Any, TYPE_CHECKING
import logging
from pathlib import Path
import json
import shutil
from shlex import quote

from . import Interface, register
from ..utils import run_cmd, randn, check_output

if TYPE_CHECKING:
    from ..runtime_env import RuntimeEnv

@register
class InterfaceDefects4J(Interface):
    NAME = 'defects4j'

    def __init__(self, env: 'RuntimeEnv'):
        super().__init__(env)

        self.proj, self.ver = env.bug_name.split('-')
        assert self.proj.isalnum()
        assert int(self.ver)>0
        self.proj = self.proj.title()
        self.ver = int(self.ver)

        self.d4j_executable: str = self._check_env_d4j()

    def save_init_data(self) -> Dict[str, Any]:
        return {
            'd4j_executable': self.d4j_executable,
        }

    def _run_d4j(self, args: str, timeout_sec: float) -> Tuple[int, float, str, str]:  # errcode, time_sec, stdout, stderr
        return run_cmd(self.d4j_executable+' '+args, timeout_sec)

    def _find_d4j(self) -> Optional[Path]:
        p = self.init_data.get('d4j_executable', None)
        if p:
            p = Path(p)
            if p.is_file():
                return p

        for root in ['/defects4j', '~/defects4j', './defects4j']:
            p = Path(root).expanduser() / 'framework/bin/defects4j'
            if p.is_file():
                logging.debug('found d4j: %s', p)
                return p

        return None

    def _check_env_d4j(self) -> str:
        d4j_exec = self._find_d4j()

        # ensure d4j is installed

        if not d4j_exec:
            try:
                d4j_exec_str = check_output('which defects4j', 5).strip()
            except Exception:
                raise RuntimeError('defects4j not found, install it and pass this parameter: --interface-config {"d4j_executable":"/path/to/defects4j/framework/bin/defects4j"}')
            logging.debug('figured out d4j from path: %s', d4j_exec_str)

            assert d4j_exec_str.endswith('/framework/bin/defects4j'), f'invalid d4j path: {d4j_exec_str}'
            d4j_exec = Path(d4j_exec_str)
            assert d4j_exec.is_file(), f'invalid d4j path: {d4j_exec_str}'

        # ensure the bug looks good (e.g. not deprecated)

        check_output(f'{d4j_exec} info -p {self.proj} -b {self.ver}', 5)

        # check java version

        javac_ver = check_output(f'javac -version', 5, check_stderr=True)
        if '1.8.' not in javac_ver:
            raise RuntimeError('invalid javac version (%s), 1.8 required'%javac_ver)

        java_ver = check_output(f'java -version', 5, check_stderr=True)
        if '1.8.' not in java_ver:
            raise RuntimeError('invalid java version (%s), 1.8 required'%java_ver)

        # done

        return str(d4j_exec.resolve())

    def _src_fixup(self, workdir: str) -> None:
        projpath = Path(workdir)

        if self.proj=='Lang' and (projpath/'src/test/org/apache/commons/lang/enum').is_dir():
            # the package name `enum` causes trouble since jdk1.5
            logging.info('src_fixup for Lang')

            assert (projpath/'src/test/org/apache/commons/lang/enums').is_dir()  # new dir should already exist
            assert (projpath/'src/java/org/apache/commons/lang/enums').is_dir()

            shutil.rmtree(projpath/'src/test/org/apache/commons/lang/enum')
            shutil.rmtree(projpath/'src/java/org/apache/commons/lang/enum')

            for p in projpath.glob('**/*.java'):
                with p.open('rb') as f:
                    src = f.read()
                src = src \
                    .replace(b'org.apache.commons.lang.enum.', b'org.apache.commons.lang.enums.') \
                    .replace(b'org.apache.commons.lang.enum;', b'org.apache.commons.lang.enums;')
                with p.open('wb') as f:
                    f.write(src)

    def _export(self, workdir: str, propname: str) -> str:
        assert Path(workdir).exists()

        resfile = Path(workdir)/f'export_{randn(6)}.txt'

        errcode, tsec, stdout, stderr = self._run_d4j(f'export -p {quote(propname)} -w {quote(workdir)} -o {resfile}', timeout_sec=90)

        assert errcode==0, 'ERRCODE=%s\nSTDERR=\n%s\n\nSTDOUT=\n%s'%(errcode, stderr, stdout)
        assert resfile.exists(), 'cannot export '+propname
        with resfile.open() as f:
            content = f.read()
        resfile.unlink()

        return content

    def checkout(self, workdir: str) -> None:
        assert not Path(workdir).exists()

        errcode, _, stdout, stderr = self._run_d4j(f'checkout -p {self.proj.title()} -v {self.ver}b -w {quote(workdir)}', timeout_sec=180)
        assert errcode==0, 'ERRCODE=%s\nSTDERR=\n%s\n\nSTDOUT=\n%s'%(errcode, stderr, stdout)
        assert Path(workdir).exists(), 'checkout path does not exist'

        self._src_fixup(workdir)

    def compile(self, workdir: str, timeout_sec: Optional[float] = None) -> Tuple[bool, float, str, str]:
        assert Path(workdir).exists()

        errcode, tsec, stdout, stderr = self._run_d4j(f'compile -w {quote(workdir)}', timeout_sec=timeout_sec)
        return errcode==0, tsec, stdout, stderr

    def test(self, workdir: str, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, List[Tuple[str, str]]]:
        assert Path(workdir).exists()
        if test:
            assert '::' in test  # test_class::test_method

        # utils_logger.setLevel(logging.CRITICAL)
        errcode, tsec, pout, perr = self._run_d4j(f'test -w {quote(workdir)} {("-t "+quote(test)) if test else ""}', timeout_sec=timeout_sec)
        # utils_logger.setLevel(logging.NOTSET)
        assert errcode==0

        line = pout.splitlines()[0]
        assert line.startswith('Failing tests: ')
        # print(pout) #####
        failcnt = int(line.partition(':')[2])

        fail_tests = []
        for ln in pout.splitlines()[1:]:
            assert ln.startswith('  - ') and '::' in ln, f'invalid d4j result line: {ln}'
            clz, method = ln[4:].split('::')
            fail_tests.append((clz, method))
        assert len(fail_tests)==failcnt

        return tsec, fail_tests

    def export_cp_compile(self, workdir: str) -> str:
        ret = self._export(workdir, 'cp.compile')

        if self.proj=='Mockito':
            # does not compile because of incomplete class path
            logging.info('classpath fixup for mockito')
            workpath = Path(workdir)

            fixup = ':'.join([
                str(p.resolve()) for p in [
                    *list(workpath.glob('lib/build/*.jar')),
                    *list(workpath.glob('lib/compile/*.jar')),
                    *list(workpath.glob('lib/repackaged/*.jar')),
                    *list(workpath.glob('lib/run/*.jar')),
                ]
            ])

            ret = f'{fixup}:{ret}'

        return ret

    def export_cp_test(self, workdir: str) -> str:
        ret = self._export(workdir, 'cp.test')

        if self.env.bug_name.lower().startswith('mockito-'):
            # does not compile because of incomplete class path
            logging.info('classpath fixup for mockito')
            workpath = Path(workdir)

            fixup = ':'.join([
                str(p.resolve()) for p in [
                    *list(workpath.glob('lib/build/*.jar')),
                    *list(workpath.glob('lib/compile/*.jar')),
                    *list(workpath.glob('lib/repackaged/*.jar')),
                    *list(workpath.glob('lib/run/*.jar')),
                    *list(workpath.glob('lib/test/*.jar')),
                ]
            ])

            ret = f'{fixup}:{ret}'

        return ret

    def export_lang_level(self, workdir: str) -> int:
        if self.proj=='Lang' and self.ver in [51, 55, 57, 59]:
            return 3  # xxx: they are reported as 1.7 in json data, which is wrong

        jsonp = self.data_path / (self.proj.lower()+'.json')
        if not jsonp.exists():
            if self.proj.lower()=='chart':
                return 4

            return 5

        with jsonp.open() as f:
            data = json.load(f)
            v = data['complianceLevel'].get(str(self.ver), None)
            if not v:
                return 5

            return v['source']

    def export_java_env(self, workdir: str) -> str:
        return 'TZ=America/Los_Angeles'

    def export_tp_src(self, workdir: str) -> str:
        return self._export(workdir, 'dir.bin.classes')

    def export_tp_test(self, workdir: str) -> str:
        return self._export(workdir, 'dir.bin.tests')

    def export_sp_src(self, workdir: str) -> str:
        return self._export(workdir, 'dir.src.classes')

    def export_sp_test(self, workdir: str) -> str:
        return self._export(workdir, 'dir.src.tests')

    def export_tests_all_class(self, workdir: str) -> List[str]:
        return self._export(workdir, 'tests.all').rstrip().split('\n')

    def export_tests_trigger(self, workdir: str) -> List[str]:
        return self._export(workdir, 'tests.trigger').rstrip().split('\n')