import time
from typing import Optional, Tuple

import d4j
from patcher import BasePatcher, VERBOSE


class NaivePatcher(BasePatcher):
    COMPILE_TIMEOUT_SEC = 120
    RUN_TEST_TIMEOUT_SEC = 600 # time for EACH patch

    def apply_patch(self, patch_id: int):
        if VERBOSE:
            print(self.workdir_s, ': apply patch', patch_id, '/', len(self.config.patches))

        assert 0<patch_id<=len(self.config.patches)

        with (self.workpath / self.config.filename).open('w') as f:
            f.write(
                self.config.context_above +
                self.config.patches[patch_id-1] +
                self.config.context_below
            )

    def restore_patch(self):
        with (self.workpath / self.config.filename).open('w') as f:
            f.write(
                self.config.context_above +
                self.config.unpatched +
                self.config.context_below
            )

    def compile(self, timeout_sec: Optional[float] = None):
        if VERBOSE:
            print('  - compile')
        return super().compile(timeout_sec=timeout_sec)

    def test(self, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, int]: # tsec, failcnt
        if VERBOSE:
            print('  - test', test or '(all)')
        return d4j.test(self.workdir_s, test, timeout_sec=timeout_sec)

    def main(self):  # patchcnt, t_compile, t_run_normal, tot_t_run_withprio, succlist
        tot_t_compile = 0
        tot_t_run_normal = 0
        tot_t_run_withprio = 0
        compiled_patches = 0
        failing_tests = self.prop('tests.trigger').split('\n')

        succlist = []

        print('main')

        for n in range(1, 1+len(self.config.patches)):
            t1 = time.time()
            self.apply_patch(n)
            comp_succ, comp_time_sec = self.compile(timeout_sec=self.COMPILE_TIMEOUT_SEC)
            t2 = time.time()
            tot_t_compile += t2-t1

            if comp_succ:
                compiled_patches += 1

                # normal

                t1 = time.time()
                try:
                    test_time_sec, failcnt = self.test(timeout_sec=self.RUN_TEST_TIMEOUT_SEC)
                except Exception: # maybe timeout
                    succlist.append('T')
                else:
                    print('  normal failcnt =', failcnt)
                    succlist.append('s' if failcnt==0 else 'F')
                t2 = time.time()
                normal_time = t2-t1
                tot_t_run_normal += normal_time

                # withprio

                withprio_time = 0
                t1 = time.time()
                for test in failing_tests:
                    if not test:
                        continue
                    try:
                        test_time_sec, failcnt = self.test(test, timeout_sec=self.RUN_TEST_TIMEOUT_SEC)
                    except Exception: # maybe timeout
                        print('  TIMEOUT')
                        break
                    else:
                        if failcnt>0:
                            print('  FAILED')
                            break
                else:
                    print('  succ all failing tests')
                    withprio_time += normal_time
                t2 = time.time()
                withprio_time += t2-t1
                tot_t_run_withprio += withprio_time


            else:
                succlist.append('C')
                if VERBOSE:
                    print('- FAILED to compile')

        return compiled_patches, tot_t_compile, tot_t_run_normal, tot_t_run_withprio, ''.join(succlist)