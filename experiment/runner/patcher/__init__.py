import json
import pathlib
import shutil
from dataclasses import dataclass
from threading import Lock
from typing import List, Optional, Tuple

import d4j
from utils import randn


VERBOSE = True
RUNNER_PATH = pathlib.Path(__file__).resolve().parent.parent
RUN_PATH = RUNNER_PATH/'run'
RUN_PATH.mkdir(exist_ok=True)
(RUNNER_PATH/'res-out').mkdir(exist_ok=True)


cache_lock = Lock()
d4j_props_cache = {} # (proj, ver) => {prop => value}


@dataclass()
class PatchConfig:
    manifest_version: int
    project: str
    version: int
    filename: str
    context_above: str
    context_below: str
    unpatched: str
    patches: List[str]

    def __post_init__(self):
        self.project = self.project.title()

        if isinstance(self.version, str):
            self.version = int(self.version)

        assert self.manifest_version==2

        #assert not self.filename.startswith('buggy/') # this is the case in manifest version 1


class BasePatcher:
    def __init__(self, config_json_path_s: str, workdir: Optional[str] = None, checkout: bool = True):
        self.jsonpath_s = config_json_path_s
        with open(config_json_path_s) as f:
            obj = json.load(f)
            self.config = PatchConfig(**obj)

        self.workdir_s = workdir or f'{str(RUN_PATH)}/{self.config.project}_{self.config.version}_{randn(6)}'
        self.workpath = pathlib.Path(self.workdir_s)
        self.configpath = pathlib.Path(config_json_path_s)

        if VERBOSE:
            print('init', self.configpath.resolve())
            print(' - tot', len(self.config.patches), 'patches')

        if checkout and not self.workpath.exists():
            self.checkout()

    def checkout(self):
        if VERBOSE:
            print('checkout', self.config.project, self.config.version)
            print(' - into', self.workpath.resolve())
            print(' - modified', (self.workpath/self.config.filename).resolve())
            print(' - line', 1+self.config.context_above.count('\n'))

        self.workpath = pathlib.Path(self.workdir_s)

        d4j.checkout(self.config.project, int(self.config.version), True, self.workdir_s)

        assert self.workpath.exists()
        with (self.workpath/'_expapr_jsonpath.txt').open('w') as f:
            f.write(self.jsonpath_s)

    def cleanup(self):
        if not self.workpath.exists(): # already cleaned up
            return

        if VERBOSE:
            print('cleanup')

        shutil.rmtree(self.workdir_s)
        self.workpath = None

    def compile(self, timeout_sec: Optional[float] = None) -> Tuple[bool, float]: # succ, tsec
        return d4j.compile(self.workdir_s, timeout_sec=timeout_sec)

    def prop(self, propname):
        k = (self.config.project, self.config.version)
        with cache_lock:
            dic = d4j_props_cache.get(k, None)
            if dic and propname in dic:
                return dic[propname]
        # cache miss
        v = d4j.export(self.workdir_s, propname)
        if self.workdir_s not in v: # does not contain workdir-related data, can be cached
            print(f'  prop cached {k} {propname} -> {v[:50]}')
            with cache_lock:
                d4j_props_cache.setdefault(k, {})[propname] = v
        return v

    def get_language_level(self) -> int:
        if self.config.project.lower()=='lang' and self.config.version in [51, 55, 57, 59]:
            return 3 # xxx: they are reported as 1.7 in json data, which is wrong

        jsonp = pathlib.Path('../defects4j-data')/(self.config.project.lower()+'.json')
        if not jsonp.exists():
            if self.config.project.lower()=='chart':
                return 4

            return 5

        with jsonp.open() as f:
            data = json.load(f)
            v = data['complianceLevel'].get(str(self.config.version), None)
            if not v:
                return 5

            return v['source']


from .naive_patcher import NaivePatcher
from .expapr_patcher import ExpAprPatcher
from .uniapr_patcher import UniAprPatcher
#from .onlyvmvm_patcher import OnlyVmvmPatcher