from typing import Optional, Tuple, List, Dict, Any, Type, TYPE_CHECKING
from pathlib import Path
import logging

if TYPE_CHECKING:
    from ..runtime_env import RuntimeEnv

class Interface:
    NAME = None

    def __init__(self, env: 'RuntimeEnv'): # perform self check here
        self.env = env
        self.init_data = env.interface_init_data
        self.data_path = Path(__file__).parent/'data'/self.NAME
        assert self.data_path.parent.exists(), f'interface data path does not exist'

    def save_init_data(self) -> Dict[str, Any]:
        """ Save arbitrary data during `cli init` command.

        @return: Any data that will be merged into env.interface_init_data
        """
        return {}

    # commands

    def checkout(self, workdir: str) -> None:
        """ Checkout the bug into a new working directory. """
        raise NotImplementedError()

    def compile(self, workdir: str, timeout_sec: Optional[float] = None) -> Tuple[bool, float, str, str]: # succ, time_sec, stdout, stderr
        """ Compile the whole project. """
        raise NotImplementedError()

    def test(self, workdir: str, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, List[Tuple[str, str]]]:  # time_sec, fail_names
        """ Run the test suite. """
        raise NotImplementedError()

    # properties

    def export_cp_compile(self, workdir: str) -> str:
        """ Classpath to compile the project. """
        raise NotImplementedError()
    def export_cp_test(self, workdir: str) -> str:
        """ Classpath to run the test suite (including the compiler output path of the project itself!). """
        raise NotImplementedError()
    def export_lang_level(self, workdir: str) -> int:
        """ Java source level of the project. """
        raise NotImplementedError()
    def export_java_env(self, workdir: str) -> str:
        """ Environment variables when running the test suite (e.g., "HTTP_PROXY=xxx HTTPS_PROXY=xxx"). """
        raise NotImplementedError()

    def export_tp_src(self, workdir: str) -> str:
        """ Location of the compiled source .class files, relative to the project root (e.g., "target/classes"). """
        raise NotImplementedError()
    def export_tp_test(self, workdir: str) -> str:
        """ Location of the compiled test .class files, relative to the project root (e.g., "target/test-classes"). """
        raise NotImplementedError()

    def export_sp_src(self, workdir: str) -> str:
        """ Location of the source .java files, relative to the project root (e.g., "src/main/java"). """
        raise NotImplementedError()
    def export_sp_test(self, workdir: str) -> str:
        """ Location of the test .java files, relative to the project root (e.g., "src/test/java"). """
        raise NotImplementedError()

    def export_tests_all_class(self, workdir: str) -> List[str]:
        """ All test classes in this project (e.g., ["com.TestA", "com.TestB"]). """
        raise NotImplementedError()
    def export_tests_trigger(self, workdir: str) -> List[str]:
        """ All failing test cases in this project (e.g., ["com.TestA::testFoo", "com.TestA::testBar"]). """
        raise NotImplementedError()

interface_mapping: Dict[str, Type[Interface]] = {}

def register(clz: Type[Interface]):
    name = clz.NAME
    assert name is not None, 'interface name not set'
    if name in interface_mapping:
        logging.warning('interface already registered: %s', name)
    interface_mapping[name] = clz
    return clz

from . import defects4j
from . import bears
from . import maven
