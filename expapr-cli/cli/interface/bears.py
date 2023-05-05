import shutil
from typing import TYPE_CHECKING, List, Optional, Tuple, Dict, Any
from pathlib import Path
import json
import logging
from shlex import quote

from . import register
from .maven import InterfaceMaven
from ..utils import run_cmd, check_output

if TYPE_CHECKING:
    from ..runtime_env import RuntimeEnv

@register
class InterfaceBears(InterfaceMaven):
    NAME = 'bears'

    def __init__(self, env: 'RuntimeEnv'):
        super().__init__(env)

        self.bug_id = env.bug_name
        if self.bug_id.startswith('Bears-'):
            self.bug_id = self.bug_id[len('Bears-'):]
        self.bug_id = int(self.bug_id)

        bears_root, bug_branch = self._check_env_bears()
        self.bears_root: str = bears_root
        self.bug_branch: str = bug_branch

    def save_init_data(self) -> Dict[str, Any]:
        all_tests, fail_tests = self._reflect_test_info()
        return {
            'bears_root': self.bears_root,
            'test_cases_failing': fail_tests,
            'test_classes': list(set([t[0] for t in all_tests])),
        }

    def _find_bears(self) -> Optional[Path]:
        p = self.env.interface_init_data.get('bears_root', None)
        if p:
            p = Path(p)
            if (p/'.git').is_dir():
                return p

        for root in ['/bears-benchmark', '~/bears-benchmark', './bears-benchmark', '/bears', '~/bears', './bears']:
            p = Path(root).expanduser()
            if (p/'.git').is_dir():
                logging.debug('found bears-benchmark: %s', p)
                return p

        return None

    def _check_env_bears(self) -> Tuple[str, str]:
        bears_path = self._find_bears()

        # ensure bears dir exists

        if not bears_path:
            raise RuntimeError('bears-benchmark directory not found, clone it and pass this parameter: --interface-config {"bears_root":"/path/to/bears-benchmark"}')

        branch_file = bears_path/'scripts/data/bug_id_and_branch.json'
        assert branch_file.is_file(), 'invalid bears-benchmark directory'

        # ensure the bug id exists

        with branch_file.open() as f:
            bugs = json.load(f)
        bug_key = f'Bears-{self.bug_id}'

        for bug in bugs:
            if bug['bugId'] == bug_key:
                bug_branch = bug['bugBranch']
                break
        else:
            raise RuntimeError(f'bug {self.bug_id} not found in bears-benchmark')

        # check java and maven

        javac_ver = check_output(f'javac -version', 5, check_stderr=True)
        if '1.8.' not in javac_ver:
            raise RuntimeError('invalid javac version (%s), 1.8 required'%javac_ver)

        java_ver = check_output(f'java -version', 5, check_stderr=True)
        if '1.8.' not in java_ver:
            raise RuntimeError('invalid java version (%s), 1.8 required'%java_ver)

        maven_ver = check_output(f'mvn -version', 5).partition('\n')[0]
        if 'Maven 3.' not in maven_ver:
            raise RuntimeError('invalid maven version (%s), 3.3.9 required'%java_ver)

        # done

        return str(bears_path.resolve()), bug_branch

    def checkout(self, workdir: str) -> None:
        assert not Path(workdir).exists()

        shutil.copytree(self.bears_root, workdir, ignore_dangling_symlinks=True) # do not touch the benchmark dir because we may run multiple instances
        check_output(f'git reset .; git checkout -- .; git clean -f; git checkout {quote(self.bug_branch)}', 30, workdir) # checkout the bug branch
        check_output('git checkout HEAD^^', 30, workdir) # to the buggy commit
        check_output('git checkout -b expapr-bear-buggy', 15, workdir) # make HEAD not dangling