import logging
import shutil
from typing import Any

from .. import utils
from ..runtime_env import RuntimeEnv, load
from .. import interface

TEST_LOCALE_SRC = '''
import java.io.IOException;
class Foo {
    void bar() {
        try {}
        catch(IOException e) {}
    }
}
'''
TEST_LOCALE_ERROR = 'error: exception IOException is never thrown in body of corresponding try statement'

def check_env(env: RuntimeEnv, args: Any):
    logging.info('== check_env')

    # ensure args looks good

    assert env.interface_name in interface.interface_mapping, f'interface not supported: {env.interface_name}'
    assert env.n_jobs>0, f'invalid number of jobs: {env.n_jobs}'

    # ensure git is installed

    utils.check_output('git --version', 5)

    # benchmark self check

    env.interface = interface.interface_mapping[env.interface_name](env)
    env.interface_init_data.update(env.interface.save_init_data())

    # ensure workdir usable

    if not env.workpath.exists():
        env.workpath.mkdir(parents=True)

    if not env.workpath.is_dir() or list(env.workpath.iterdir())!=[]:
        if args.reuse_workdir:
            if (env.workpath/'env.json').is_file():
                # noinspection PyBroadException
                try:
                    old_env = load(env.workpath/'env.json')
                    assert old_env.env_version==2
                    assert old_env.interface_name==env.interface_name
                    assert old_env.bug_name==env.bug_name

                    env.applicable_tests = old_env.applicable_tests

                    logging.info('loaded test info from original env: %d tests', len(env.applicable_tests))
                except Exception:
                    logging.exception('reuse test info from env failed')

            logging.warning('workdir not empty, removing everything inside as requested')
            for p in env.workpath.iterdir():
                if p.is_dir():
                    shutil.rmtree(p)
                else:
                    p.unlink()
        else:
            raise RuntimeError('invalid workdir, must be an empty directory: %s'%env.workpath)

    # ensure compiler error msg locale looks good

    with (env.workpath/'Foo.java').open('w') as f:
        f.write(TEST_LOCALE_SRC)

    msg = utils.check_output(f'javac -J-Duser.language=en -nowarn -Xmaxerrs 1 Foo.java', 10, str(env.workpath), expect_errcode=1, check_stderr=True)
    if TEST_LOCALE_ERROR not in msg:
        raise RuntimeError('cannot recognize javac output: %s'%msg)

    (env.workpath/'Foo.java').unlink()
