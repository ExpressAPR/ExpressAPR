import json
import pathlib
import logging
from typing import Optional, Tuple, List, Dict, Any

from .. import patch_config
from ..runtime_env import RuntimeEnv


PROPS_GLOBAL_CACHE: Dict[str, Any] = {}


def common_pfx_len(a, b):
    for i in range(min(len(a), len(b))):
        if a[i] != b[i]:
            return i
    return min(len(a), len(b))


def prioritize_tests(tests_all: List[Tuple[str, str, int]], tests_trigger: List[str], patched_class_name: str) -> List[Tuple[str, str, int]]:
    def filter_test_name(ts: List[Tuple[str, str, int]]) -> List[Tuple[str, str, int]]:
        # `$`: sometimes we get com.google.javascript.jscomp.SpecializeModuleTest$SpecializeModuleSpecializationStateTest
        return [t for t in ts if ('$' not in t[0]) and ('.enum.' not in t[0])]

    tests_trigger = set([
        (cls, mtd)
        for cls, mtd, _t in
        filter_test_name([(clz, mtd, 0) for x in tests_trigger for clz, _, mtd in [x.partition('::')]])
    ])

    def sort_key(t: Tuple[str, str, int]):
        trigger_key = 0 if (t[0], t[1]) in tests_trigger else 1
        pkg_key = 0 - common_pfx_len(patched_class_name, t[0].replace('Test', ''))
        time_key = t[2]

        return trigger_key, pkg_key, time_key

    tests = sorted(filter_test_name(tests_all), key=sort_key)
    return tests


def get_class_name_from_fn(java_fn, root_fn):
    # e.g. java_fn = 'source/org/jfree/chart/renderer/category/AbstractCategoryItemRenderer.java'
    #      root_fn = 'source'
    if not java_fn.startswith(root_fn) or not java_fn.endswith('.java'):
        return ''
    java_fn = java_fn[len(root_fn):-5]
    if java_fn.startswith('/'):
        java_fn = java_fn[1:]

    return java_fn.replace('/', '.')



class BasePatcher:
    def __init__(self, config_json_path_s: str, env: RuntimeEnv, eidx: int):
        self.jsonpath_s = config_json_path_s
        with open(config_json_path_s) as f:
            obj = json.load(f)
            self.config = patch_config.load(obj)

        assert self.config.interface==env.interface_name, f'interface mismatch: {env.interface_name} in env but {self.config.interface} in patches'
        assert self.config.bug==env.bug_name, f'bug mismatch: {env.bug_name} in env but {self.config.bug} in patches'

        self.cur_env = env.projects[eidx]

        self.props_cache = self.cur_env['props']
        self.workdir_s = str(self.cur_env['root'])
        self.workpath = self.cur_env['root']
        self.configpath = pathlib.Path(config_json_path_s)
        self.env = env

        assert self.workpath.is_dir()

        logging.info('%s init: %s', type(self).__name__, self.configpath.resolve())
        logging.debug('- tot %d patches', len(self.config.patches))

    def compile(self, timeout_sec: Optional[float] = None) -> Tuple[bool, float]: # succ, tsec
        succ, tsec, _stdout, _stderr = self.env.interface.compile(self.workdir_s, timeout_sec=timeout_sec)
        return succ, tsec

    def prop(self, propname: str) -> Any:
        if propname in self.props_cache:
            return self.props_cache[propname]

        if propname in PROPS_GLOBAL_CACHE:
            val = PROPS_GLOBAL_CACHE[propname]
            self.props_cache[propname] = val
            return val

        # cache miss
        v = getattr(self.env.interface, f'export_{propname}')(self.workdir_s)
        logging.info('got prop %s -> %s', propname, repr(v)[:50])
        self.props_cache[propname] = v

        return v

    def fixup_if_needed(self):
        pass


from .expapr_patcher import ExpAprPatcher
from .onlyvmvm_patcher import OnlyVmvmPatcher
from .fallback_patcher import FallbackPatcher