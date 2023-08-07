from typing import List
from queue import Queue
import threading
import json
import logging
import traceback
import time
from typing import Callable, Any

from .techniques import TECHNIQUES
from ..runtime_env import RuntimeEnv

MAX_N_JOBS = None

quit_symbol = lambda: None

def thread(env: RuntimeEnv, q: Queue, idx0: int, notify: Callable[[Any], None], args: Any):
    logger = logging.getLogger(f'thread-{idx0}')
    logger.info('worker started')

    techs = [(t_name, TECHNIQUES[t_name](env, idx0, args)) for t_name in args.technique]

    while True:
        jsonpath = q.get()

        if jsonpath is quit_symbol:
            logger.info('worker quit')
            for _, tech in techs:
                tech.shutdown()
            return

        extras = {
            'timestamp_begin': time.time(),
        }

        try:
            logger.info('== (%d left) %s', q.qsize(), jsonpath)

            for t_name, tech in techs:
                succlist, new_extras = tech.run(jsonpath)
                extras.update(new_extras)

                if succlist is not None:
                    logger.info(' -> (%s) [%s] for %s', t_name, succlist, jsonpath)
                    extras.update({
                        'timestamp_end': time.time(),
                    })
                    notify({
                        'patches_path': jsonpath,
                        'technique': t_name,
                        'succlist': succlist,
                        'extra': extras,
                    })
                    break
                else: # succlist is None
                    logger.info(' -> (%s) !FAIL for %s', t_name, jsonpath)
                    logger.debug('    %s', new_extras)

            else: # all techniques failed
                logger.warning(' -> all tech failed for %s', jsonpath)
                extras.update({
                    'timestamp_end': time.time(),
                })
                notify({
                    'patches_path': jsonpath,
                    'technique': None,
                    'succlist': None,
                    'extra': extras,
                })

        except Exception as e:
            logger.exception(e)
            extras.update({
                'timestamp_end': time.time(),
                'worker_error_type': type(e).__name__,
                'worker_error_repr': repr(e),
                'worker_error_trace': traceback.format_exc(),
            })
            notify({
                'patches_path': jsonpath,
                'technique': None,
                'succlist': None,
                'extra': extras,
            })

        finally:
            q.task_done()

def dispatch(env: RuntimeEnv, patches: List[str], args: Any):
    if not patches:
        logging.info('nothing to do')
        return

    q = Queue()
    for p in patches:
        q.put(p)

    result_lock = threading.Lock()

    n_workers = env.n_jobs if MAX_N_JOBS is None else min(env.n_jobs, MAX_N_JOBS)
    logging.info('starting %d workers', n_workers)

    with open(env.workpath/'result.jsonl', 'a') as f:

        def notifier(item):
            with result_lock:
                f.write(json.dumps(item)+'\n')
                f.flush()

        threads = []
        for i in range(n_workers):
            t = threading.Thread(target=thread, args=(env, q, i, notifier, args))
            t.start()
            threads.append(t)

        q.join()

        for i in range(n_workers):
            q.put(quit_symbol)

        for t in threads:
            t.join()