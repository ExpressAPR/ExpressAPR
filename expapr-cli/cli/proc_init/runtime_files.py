import shutil
import logging
from pathlib import Path
from typing import Any

from cli.runtime_env import RuntimeEnv
from ..patcher import ExpAprPatcher, PROPS_GLOBAL_CACHE
from ..utils import check_output, copy_tree_retry
from .. import servant_connector

PSEUDO_PATCH_JSON = '''{
	"manifest_version": 3,

	"interface": "[[[INTERFACE]]]",
	"bug": "[[[BUG]]]",

    "filename": "",
    "context_above": "",
    "unpatched": "",
    "context_below": "",
    "patches": []
}'''

def write_pseudo_json(env: RuntimeEnv):
    jsonpath = env.workpath/'pseudo.json'
    with jsonpath.open('w') as f:
        f.write(
            PSEUDO_PATCH_JSON
                .replace('[[[INTERFACE]]]', env.interface_name)
                .replace('[[[BUG]]]', env.bug_name)
        )

def clone_project(env: RuntimeEnv) -> Path:
    proj_root = env.workpath/'repo-buggy'

    logging.info('clone_project for %s', env.bug_name)
    env.interface.checkout(str(proj_root))

    return proj_root

def _can_be_related(s: str, c: Any) -> bool:
    if isinstance(c, str):
        return s in c
    if isinstance(c, int):
        return s in str(c)
    if isinstance(c, bool):
        return False
    if isinstance(c, list) or isinstance(c, tuple):
        return any(_can_be_related(s, x) for x in c)
    if isinstance(c, dict):
        return any(_can_be_related(s, x) for x in c.keys()) or any(_can_be_related(s, x) for x in c.values())

    raise RuntimeError(f'unknown type: {type(c)}')

def copy_runtime_files(env: RuntimeEnv, eidx: int):
    logging.info('== copy_runtime_files')

    con = servant_connector.ServantConnector(
        enable_assertion=True,
        igniter_path=Path('../expapr-jar'),
    )

    # set purity source: not really necessary, just to check the correctness of purity source

    status, rpc_res = con.request_on_startup({
        'action': 'setup',
        'purity_source': env.deduplication,
    }, 30)

    if status!='succ':
        logging.critical('purity source setup failed: %s', rpc_res)
        raise RuntimeError('purity source setup failed')

    # tag untouched

    src_proj = env.projects[eidx]

    check_output('git tag EXPAPR_UNTOUCHED', 15, cwd=src_proj['root'])

    # tag interface original

    p = ExpAprPatcher(env.workpath/'pseudo.json', env, eidx)
    p.precompile_code()

    check_output('git add .', 30, cwd=str(src_proj['root']))
    check_output('git commit --allow-empty -m "EXPAPR: interface original"', 30, cwd=str(src_proj['root']))
    check_output('git tag EXPAPR_INTERFACE_ORIGINAL', 15, cwd=str(src_proj['root']))

    # copy multiple workdirs

    projects = []
    for j in range(1, env.n_jobs+1):
        copy_tree_retry(src_proj['root'], env.workpath/f'repo-buggy-{j}')

        projects.append({
            'root': env.workpath/f'repo-buggy-{j}',
            'props': {},
        })
    env.projects = projects

    shutil.rmtree(src_proj['root'])

    # add to global cache

    PROPS_GLOBAL_CACHE.clear()
    for k, v in p.props_cache.items():
        if not _can_be_related(str(src_proj['root']), v):
            logging.debug('add to props global cache: %s -> %s', k, repr(v)[:50])
            PROPS_GLOBAL_CACHE[k] = v

    # finish up each workdir

    for j in range(len(env.projects)):
        logging.info('== prepare workdir for #%d', j+1)
        p = ExpAprPatcher(env.workpath/'pseudo.json', env, j)

        # xxx: d4j export cleans the output directory, which sucks
        check_output('git reset EXPAPR_INTERFACE_ORIGINAL --hard && git clean -d -f', 30, cwd=p.workdir_s)

        # tag runtime injected
        # we do not put it above because after runtime files are injected, d4j export will be broken for jdk1.3 projects

        p.install_instrumentation_servant('init', con)
        p.compile_runtime_main()

        src_proj = env.projects[j]

        check_output('git add .', 30, cwd=str(src_proj['root']))
        check_output('git commit -m "EXPAPR: runtime injected"', 30, cwd=str(src_proj['root']))
        check_output('git tag EXPAPR_RUNTIME_INJECTED', 15, cwd=str(src_proj['root']))

    # restore global cache for good

    PROPS_GLOBAL_CACHE.clear()

    con.shutdown()