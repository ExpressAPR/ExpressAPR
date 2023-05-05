import random
import subprocess
import time
from typing import Optional, Tuple
from threading import get_ident
import psutil

DEBUG = False
cgidx_map = {} # tid: cgidx

def kill_tree(parent_pid): # https://psutil.readthedocs.io/en/latest/#kill-process-tree
    p = psutil.Process(parent_pid)
    ps = p.children(recursive=True)
    ps.append(p)
    print('! KILLING', parent_pid, ps)

    for proc in ps:
        try:
            proc.kill()
        except psutil.NoSuchProcess:
            pass

def run_cmd(cmdline: str, timeout_sec: Optional[float] = None, cwd: Optional[str] = None) -> Tuple[int, float, str, str]:  # errcode, time_sec, stdout, stderr
    if get_ident() in cgidx_map:
        CPUSET = cgidx_map[get_ident()]
        #print('running on cg', CPUSET)
        cmdline = f'cgexec -g cpuset:expressapr-exp-{CPUSET} {cmdline}'

    p = subprocess.Popen(
        cmdline, cwd=cwd,
        shell=True,
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    t1 = time.time()

    try:
        pout, perr = p.communicate(timeout=timeout_sec)
        errcode = p.wait()
    except subprocess.TimeoutExpired:
        kill_tree(p.pid)
        pout, perr = p.communicate(timeout=timeout_sec)
        errcode = -1337

    t2 = time.time()

    if errcode and DEBUG:
        print('POUT >>', pout.decode('utf-8', 'ignore'))
        print('PERR >>', perr.decode('utf-8', 'ignore'))

    return errcode, t2-t1, pout.decode('utf-8', 'replace'), perr.decode('utf-8', 'replace')

def randn(n):
    ALPHABET = 'qwertyuiopasdfghjklzxcvbnm'
    return ''.join([random.choice(ALPHABET) for _ in range(n)])