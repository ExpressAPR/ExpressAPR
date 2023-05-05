import patcher
import pathlib
import threading
from tqdm.contrib.concurrent import thread_map
import csv
from utils import cgidx_map
import traceback
import random
import sys
import const

APR = sys.argv[1]
THREADS = const.N_WORKERS
RES_FN = f'res-out/{APR}-uniapr-res.csv'

print('write into', RES_FN)

file_lock = threading.Lock()
cgidx_lock = threading.Lock()

def proc_json(jsonpath):
    with cgidx_lock:
        tid = threading.get_ident()
        if tid not in cgidx_map:
            cgidx = len(cgidx_map)+1
            assert cgidx<=THREADS
            print('assign cgroup', cgidx, 'to thread', tid)
            cgidx_map[tid] = cgidx

    def work():
        p = None
        try:
            p = patcher.UniAprPatcher(str(jsonpath))
            patchcnt, t_compile, t_run, succlist, telemetry = p.main()
            p.cleanup()
            return ['succ', str(jsonpath), patchcnt, t_compile, t_run, succlist, telemetry]
        except Exception as e:
            tbmsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            if p is not None:
                p.cleanup()
            return ['FAIL', str(jsonpath), tbmsg]

    res = work()

    with file_lock:
        with open(RES_FN, 'a', newline='') as f:
            w = csv.writer(f)
            w.writerow(res)

jsonpaths = list(pathlib.Path(f'../apr_tools/{APR}/patches-out').glob('**/*.json'))
random.seed(666)
random.shuffle(jsonpaths)

thread_map(proc_json, jsonpaths, max_workers=THREADS, miniters=1)