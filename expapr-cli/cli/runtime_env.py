from dataclasses import dataclass
import logging
import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

from .interface import Interface

@dataclass()
class RuntimeEnv:
    env_version: int

    interface_name: str
    bug_name: str
    interface: Optional[Interface]
    interface_init_data: Dict[str, Any]
    n_jobs: int

    workpath: Path
    projects: List[Any] # {"root": Path("/..."), "props": {"k": "v", ...}}

    applicable_tests: List[Tuple[str, str, int]]

    deduplication: Dict[str, Any]

def dump(env: RuntimeEnv):
    logging.info('dump env file')
    with Path(env.workpath/'env.json').open('w') as f:
        json.dump({
            'env_version': env.env_version,

            'interface_name': env.interface_name,
            'bug_name': env.bug_name,
            'interface_init_data': env.interface_init_data,
            'n_jobs': env.n_jobs,

            'workpath': str(env.workpath),
            'projects': [{
                'root': str(p['root']),
                'props': p['props'],
            } for p in env.projects],
            'applicable_tests': env.applicable_tests,

            'deduplication': env.deduplication,
        }, f, indent=1)

def load(envfile_path: Path) -> RuntimeEnv:
    with envfile_path.open() as f:
        env_cfg = json.load(f)
        assert env_cfg['env_version']==2

        env = RuntimeEnv(
            env_version=env_cfg['env_version'],

            interface_name=env_cfg['interface_name'],
            bug_name=env_cfg['bug_name'],
            interface=None,
            interface_init_data=env_cfg['interface_init_data'],
            n_jobs=env_cfg['n_jobs'],

            workpath=Path(env_cfg['workpath']),
            projects=[{
                'root': Path(p['root']),
                'props': p['props'],
            } for p in env_cfg['projects']],
            applicable_tests=env_cfg['applicable_tests'],

            deduplication=env_cfg['deduplication'],
        )

    assert env.workpath == envfile_path.parent.resolve()
    assert env.n_jobs==len(env.projects)

    for p in env.projects:
        assert p['root'].is_dir()
        assert p['root'].parent == env.workpath

    return env