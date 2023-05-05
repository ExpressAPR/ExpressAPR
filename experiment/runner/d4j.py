import pathlib
import os
from functools import lru_cache
from typing import Union, Tuple, Optional
from shlex import quote
from threading import get_ident
from utils import run_cmd, randn
import const

d4j_path_map = {} # tid: d4j_path

DEFAULT_D4J_PATH = const.D4J_PATH[0]

def get_d4j_path():
    return d4j_path_map.get(get_ident(), DEFAULT_D4J_PATH)

def _run_d4j(args: str, timeout_sec: float) -> Tuple[int, float, str, str]:  # errcode, time_sec, stdout, stderr
    d4j_path = d4j_path_map.get(get_ident(), DEFAULT_D4J_PATH)
    d4j_exec = os.path.join(d4j_path, 'framework/bin/defects4j')
    return run_cmd(d4j_exec+' '+args, timeout_sec)

def checkout(proj: str, ver: Union[int, str], is_buggy: bool, workdir: str):
    assert proj.isalnum()
    assert int(ver)>0
    assert not pathlib.Path(workdir).exists()

    errcode, _, stdout, stderr = _run_d4j(f'checkout -p {proj.title()} -v {ver}{"b" if is_buggy else "f"} -w {quote(workdir)}', timeout_sec=120)
    assert errcode==0, 'ERRCODE=%s\nSTDERR=\n%s\n\nSTDOUT=\n%s'%(errcode, stderr, stdout)
    assert pathlib.Path(workdir).exists(), 'checkout path does not exist'

def compile(workdir: str, timeout_sec: Optional[float] = None) -> Tuple[bool, float]: # succ, tsec
    assert pathlib.Path(workdir).exists()

    errcode, tsec, *_ = _run_d4j(f'compile -w {quote(workdir)}', timeout_sec=timeout_sec)
    return errcode==0, tsec

def compile_verbose(workdir: str, timeout_sec: Optional[float] = None) -> Tuple[bool, float, str, str]: # succ, tsec, stdout, stderr
    assert pathlib.Path(workdir).exists()

    errcode, tsec, stdout, stderr = _run_d4j(f'compile -w {quote(workdir)}', timeout_sec=timeout_sec)
    return errcode==0, tsec, stdout, stderr

def test(workdir: str, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, int]: # tsec, failcnt
    assert pathlib.Path(workdir).exists()
    if test:
        assert '::' in test # test_class::test_method

    errcode, tsec, pout, perr = _run_d4j(f'test -w {quote(workdir)} {("-t "+quote(test)) if test else ""}', timeout_sec=timeout_sec)
    assert errcode==0

    line = pout.splitlines()[0]
    assert line.startswith('Failing tests: ')
    print(pout) #####
    failcnt = int(line.partition(':')[2])

    return tsec, failcnt

@lru_cache()
def export(workdir: str, propname: str) -> str:
    assert pathlib.Path(workdir).exists()

    resfile = pathlib.Path(workdir)/f'export_{randn(6)}.txt'

    errcode, tsec, stdout, stderr = _run_d4j(f'export -p {quote(propname)} -w {quote(workdir)} -o {resfile}', timeout_sec=30)

    assert errcode==0, 'ERRCODE=%s\nSTDERR=\n%s\n\nSTDOUT=\n%s'%(errcode, stderr, stdout)
    assert resfile.exists(), 'cannot export '+propname
    with resfile.open() as f:
        content = f.read()
    resfile.unlink()

    return content