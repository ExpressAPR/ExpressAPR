from pathlib import Path
import logging
import shutil
from typing import Optional

from ..runtime_env import RuntimeEnv

def setup_dedup(dedup_arg: Optional[str], env: RuntimeEnv):
    if dedup_arg is None:
        logging.info('dedup disabled')
        env.deduplication = {
            'type': 'disabled',
        }

    elif dedup_arg == 'trivial':
        logging.info('dedup set to trivial mode')
        env.deduplication = {
            'type': 'trivial',
        }

    elif dedup_arg.startswith('sidefx_db='):
        db_path = dedup_arg[len('sidefx_db='):]
        if not Path(db_path).is_file():
            raise ValueError(f'sidefx db does not exist: {db_path}')

        shutil.copy(db_path, env.workpath/'sidefx_db.txt')

        logging.info('dedup set to sidefx_db mode')
        env.deduplication = {
            'type': 'sidefx_db',
            'sidefx_db_path': str(env.workpath/'sidefx_db.txt'),
        }

    else:
        raise ValueError(f'unknown dedup arg: {dedup_arg}')