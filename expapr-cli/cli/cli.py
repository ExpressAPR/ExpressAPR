import argparse
from pathlib import Path
import shutil
import os
import logging
import json
import time
from typing import Optional, List

import cli.proc_init.runtime_files
from . import runtime_env
from . import interface
from .utils import copy_tree_retry
from .proc_init import check_env, check_vmvm, runtime_files, dedup_config
from .proc_run import glob_patches, dispatcher, techniques

def do_init(args):
    #print('init', args)

    env = runtime_env.RuntimeEnv(
        env_version=2,
        interface_name=args.interface,
        bug_name=args.bug,
        interface=None,
        interface_init_data=json.loads(args.interface_config),
        n_jobs=args.jobs,
        workpath=Path(args.workdir).resolve(),
        projects=[],
        applicable_tests=[],
        deduplication={'type': 'disabled'},
    )

    time_begin = time.time()

    check_env.check_env(env, args)

    dedup_config.setup_dedup(args.dedup, env) # should be put above os.chdir because it may use relative path

    old_cwd = os.getcwd()
    os.chdir(Path( __file__ ).parent) # patcher and jars expect relative paths

    try:
        runtime_files.write_pseudo_json(env)

        proj_buggy_root = cli.proc_init.runtime_files.clone_project(env)

        proj_vmvmtmp_root = proj_buggy_root.with_name('repo-vmvmtmp')
        copy_tree_retry(proj_buggy_root, proj_vmvmtmp_root)

        env.projects = [
            {
                'root': proj_buggy_root,
                'props': {},
                'lang_level': None,
            },
            {
                'root': proj_vmvmtmp_root,
                'props': {},
                'lang_level': None,
            },
        ]

        if not env.applicable_tests:
            check_vmvm.check_vmvm(env, 1) # [1] is the vmvmtmp root

        runtime_files.copy_runtime_files(env, 0)

        (env.workpath/'pseudo.json').unlink()
        shutil.rmtree(proj_vmvmtmp_root)

        runtime_env.dump(env)

        time_end = time.time()

        logging.info('== DONE in %.2f seconds.', time_end-time_begin)
        logging.info('use "cli run" to start validating.')

    finally:
        os.chdir(old_cwd)

def do_run(args):
    # print('run', args)

    wp = Path(args.workdir).resolve()
    env = runtime_env.load(wp/'env.json')
    patches = glob_patches.glob_patches(env, args.patches, args.continue_from)

    assert env.interface_name in interface.interface_mapping, f'interface not supported: {env.interface_name}'
    env.interface = interface.interface_mapping[env.interface_name](env)

    old_cwd = os.getcwd()
    os.chdir(Path(__file__).parent)  # patcher and jars expect relative paths

    try:
        time_begin = time.time()

        dispatcher.dispatch(env, patches, args)

        time_end = time.time()

        logging.info('== DONE in %.2f seconds.', time_end-time_begin)
        logging.info('result written into "result.jsonl" in the working directory.')

    finally:
        os.chdir(old_cwd)

def parse_technique(s):
    l = s.split(',')
    for t in l:
        if t not in techniques.TECHNIQUES.keys():
            raise argparse.ArgumentTypeError('invalid technique: ' + t)
    return l

parser = argparse.ArgumentParser(prog='cli', description='ExpressAPR CLI')
parser.add_argument('--verbosity', type=str, default='INFO', help='the log level (DEBUG, INFO, WARNING, ERROR; default is INFO)')

subparsers = parser.add_subparsers()

parser_init = subparsers.add_parser('init', help='initialize ExpressAPR')
parser_init.add_argument('-i', '--interface', type=str, default='defects4j', help='benchmark interface to use')
parser_init.add_argument('-b', '--bug', type=str, required=True, help='the bug under validation (e.g., "Chart-1" for defects4j)')
parser_init.add_argument('-w', '--workdir', type=str, required=True, help='directory to store temporary runtime files, should be empty or nonexistent')
parser_init.add_argument('-j', '--jobs', type=int, metavar='N', default=1, help='number of threads during validation')
parser_init.add_argument('-d', '--dedup', type=str, help='side-effect data file path ("trivial"; "sidefx_db=/path/to/db.txt"; omit this to disable patch deduplication at all)')
parser_init.add_argument('--interface-config', type=str, default='{}', help='interface-specific configuration as JSON dict (default is {})')
parser_init.add_argument('--reuse-workdir', action='store_true', help='reuse the working directory, deleting everything inside (otherwise ExpressAPR will report an error and exit)')
parser_init.set_defaults(_do_func=do_init)

parser_run = subparsers.add_parser('run', help='run validation for a set of patch clusters')
parser_run.add_argument('-w', '--workdir', type=str, required=True, help='working directory as passed to the `init` command')
parser_run.add_argument('patches', nargs='+', type=str, help='glob patterns of patch cluster files to validate (e.g., `/path/to/patches/**/*.json`)')
parser_run.add_argument('-t', '--technique', dest='technique', default='expapr,fallback', type=parse_technique, help='technique to use (default: "expapr,fallback")')
parser_run.add_argument('--continue', dest='continue_from', type=glob_patches.ContinueArgs, default='ONLYSUCC', help='whether to skip finished clusters (YES, ONLYSUCC, NO; default is ONLYSUCC)')
parser_run.add_argument('--no-dedup', action='store_true', help='disable patch deduplication (even if `-d` is set in init)')
parser_run.add_argument('--no-prio', action='store_true', help='disable test case prioritization')
parser_run.set_defaults(_do_func=do_run)

def main(cmdline: Optional[List[str]] = None):
    args = parser.parse_args(cmdline)
    logging.basicConfig(
        level=getattr(logging, args.verbosity.upper()),
        format='%(asctime)s [%(levelname)s %(name)s] %(message)s',
    )

    if '_do_func' in args:
        # noinspection PyProtectedMember
        args._do_func(args)
    else:
        parser.print_help()