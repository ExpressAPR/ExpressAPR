import patcher
import pathlib
import threading
from tqdm.contrib.concurrent import thread_map
import csv
from utils import cgidx_map
import traceback
import random
import psutil
import sys
import const

THREADS = const.N_WORKERS
APR = sys.argv[1]
RES_FN = f'res-out/{APR}-naive-uniform-res.csv'

print('write into', RES_FN)

file_lock = threading.Lock()
cgidx_lock = threading.Lock()

def clean_cgroup(name): # kill all processes in given cgroup
    with open(f'/sys/fs/cgroup/cpuset/{name}/tasks') as f:
        pids = f.read().splitlines()

    for pid in pids:
        if pid:
            try:
                psutil.Process(int(pid)).kill()
            except psutil.NoSuchProcess:
                pass

def proc_json(jsonpath):
    with cgidx_lock:
        tid = threading.get_ident()
        if tid not in cgidx_map:
            cgidx = len(cgidx_map)+1
            assert cgidx<=THREADS
            print('assign cgroup', cgidx, 'to thread', tid)
            cgidx_map[tid] = cgidx
        else:
            cgidx = cgidx_map[tid]

    clean_cgroup(f'expressapr-exp-{cgidx}')

    def work():
        try:
            p = patcher.NaivePatcher(str(jsonpath))
            naive_patchcnt, naive_t_compile, naive_t_run_normal, naive_t_run_withprio, succlist = p.main()
            p.cleanup()
            return ['succ', str(jsonpath), naive_patchcnt, naive_t_compile, naive_t_run_normal, naive_t_run_withprio, succlist]
        except Exception as e:
            tbmsg = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
            return ['FAIL', str(jsonpath), tbmsg]

    res = work()

    with file_lock:
        with open(RES_FN, 'a', newline='') as f:
            w = csv.writer(f)
            w.writerow(res)

jsonpaths = list(pathlib.Path(f'../apr_tools/{APR}/patches-out').glob('**/*.json'))
random.seed(666)
random.shuffle(jsonpaths)

# skip succes clusters
# with open(RES_FN, 'r', newline='') as f:
#     r = csv.reader(f)
#     succ_tests = [pathlib.Path(row[1]) for row in r if row[0]=='succ']
#     jsonpaths = [p for p in jsonpaths if p not in succ_tests]

print('tot', len(jsonpaths))

thread_map(proc_json, jsonpaths, max_workers=THREADS, miniters=1)