import logging
import math

from ..patcher import OnlyVmvmPatcher
from ..runtime_env import RuntimeEnv

def convert_to_timeout(time_s: str) -> int:
    if time_s == 'SKIP':
        time_s = 0
    # follow existing work (e.g. PRF) for test timeout
    return math.floor(5 + float(time_s) * 1.5)

def check_vmvm(env: RuntimeEnv, eidx: int):
    logging.info('== check_vmvm')

    _tsec, should_fail_names = env.interface.test(str(env.projects[eidx]['root']), timeout_sec=15*60)

    logging.info(f'num of failing tests: {len(should_fail_names)}')

    vmvm = OnlyVmvmPatcher(env.workpath/'pseudo.json', env, eidx)
    test_measures = vmvm.main()

    def should_skip(clz, method, time_s):
        if (clz, method) in should_fail_names:
            return False
        return time_s=='SKIP'

    env.applicable_tests = [
        (clz, method, convert_to_timeout(time_s))
        for t in test_measures
        for clz, method, time_s in [t.split('::')]
        if not should_skip(clz, method, time_s)
    ]

    skipped_tests = [
        (clz, method)
        for t in test_measures
        for clz, method, time_s in [t.split('::')]
        if should_skip(clz, method, time_s)
    ]

    logging.info('skipped tests: %d / %d', len(skipped_tests), len(test_measures))
    for t in skipped_tests[:10]:
        logging.info('- %s::%s', t[0], t[1])
    if len(skipped_tests) > 10:
        logging.info('- ...')