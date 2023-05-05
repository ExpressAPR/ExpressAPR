from typing import List
from pathlib import Path
import logging
import json
import enum

from ..runtime_env import RuntimeEnv

class ContinueArgs(enum.Enum):
    ALL = 'ALL'
    ONLYSUCC = 'ONLYSUCC'
    NO = 'NO'

def remove_duplicate(li: list) -> list:
    # remove duplicate while preserving order
    # it depends on the fact (spec after Python 3.7) that dict keys are ordered
    return list(dict.fromkeys(li).keys())

def remove_completed(li: List[str], env: RuntimeEnv, continue_from: ContinueArgs) -> List[str]:
    done = set()
    result_path = env.workpath/'result.jsonl'
    if result_path.is_file():
        with result_path.open() as f:
            for l in f.read().splitlines():
                result = json.loads(l)
                if continue_from==ContinueArgs.ONLYSUCC and result['succlist'] is None:
                    continue
                done.add(result['patches_path'])

        ret = [s for s in li if s not in done]
        logging.info('found %d completed patches, %d left', len(done), len(ret))
        return ret
    else:
        return li

def glob_patches(env: RuntimeEnv, patterns: List[str], continue_from: ContinueArgs) -> List[str]:
    basepath = Path('.')
    patches = []

    for pattern in patterns:
        if pattern.startswith('/'):
            basepath = Path('/')
            pattern = pattern[1:]

        patches.extend(str(p.resolve()) for p in basepath.glob(pattern))

    patches = remove_duplicate(patches)

    if len(patches)==len(patterns)>=100:
        logging.warning('you have specified %d glob patterns. did you forget to quote the pattern to avoid shell expansion?', len(patterns))

    logging.info('globbed %d patches from %d pattern%s', len(patches), len(patterns), '' if len(patterns)==1 else 's')

    if continue_from!=ContinueArgs.NO:
        patches = remove_completed(patches, env, continue_from)

    return patches