import time
import logging
from shlex import quote
import javalang
import javalang.tree
from typing import Optional, Tuple, Dict, List

from . import BasePatcher
from ..runtime_env import RuntimeEnv
from ..utils import run_cmd
from ..utils import log as utils_logger


MARKER_FN = '_expapr_touch_marker.txt'
USE_TOUCH_MARKER = False


def add_touch_marker(src_above: str, src_patched: str, src_below: str) -> Tuple[bool, str]:
    src_full = src_above + src_patched + src_below
    patched_line_begin = src_above.count('\n')+1
    patched_line_end = patched_line_begin+src_patched.count('\n')

    tokens = list(javalang.tokenizer.tokenize(src_full))
    pos_idx = {id(t.position): idx for idx, t in enumerate(tokens)}

    tree = javalang.parser.Parser(tokens).parse()
    classes = sorted(tree.types, key=lambda c: c.position.line)

    marker_positions = []

    for i, c in enumerate(classes):
        # is this declaration patched?

        if c.position.line>patched_line_end:
            # this decl passed patch end
            break
        if i<len(classes)-1 and c.position.line<patched_line_begin and classes[i+1].position.line<=patched_line_begin:
            # this decl does not reach patch begin
            continue

        # can marker added here?

        if not (isinstance(c, javalang.tree.ClassDeclaration) or isinstance(c, javalang.tree.EnumDeclaration)):
            # cannot add static initializer in other types (eg interface and annotation decl)
            return False, src_full

        if c.position is None or id(c.position) not in pos_idx:
            # should not happen
            return False, src_full

        # find the corresponding `}` to add marker

        ti = pos_idx[id(c.position)]

        tend = ti+1
        level = 0
        while tend<len(tokens):
            tok = tokens[tend]

            if tok.value=='{':
                level += 1
            elif tok.value=='}':
                level -= 1
                if level<=0:
                    break

            tend += 1

        if not (level==0 and tend<len(tokens) and tokens[tend].value=='}'):
            # corresponding `}` not found, should not happen
            return False, src_full

        marker_positions.append(tend)

    if len(marker_positions)==0:
        # it is possible that no class is patched at all, but it seems so weird, so just skip it for sanity
        return False, src_full

    # add marker from end to begin, so the idx stays correct

    marker_stmt = '''static {
        try {
            new java.io.File("__FILENAME__").createNewFile();
        } catch (java.io.IOException e) {
            throw new RuntimeException(e);
        }
    }'''.replace('__FILENAME__', MARKER_FN)

    chunks = [str(t.value) for t in tokens]

    for pos in marker_positions[::-1]:
        chunks.insert(pos, marker_stmt)

    logging.debug('installed marker at %s positions', len(marker_positions))
    return True, ' '.join(chunks)


class FallbackPatcher(BasePatcher):
    COMPILE_TIMEOUT_SEC = 120
    RUN_ALL_TEST_TIMEOUT_SEC = 300 # time for EACH patch

    def __init__(self, jsonpath, env: RuntimeEnv, eidx: int, noprio = False):
        super().__init__(jsonpath, env, eidx)

        self.nodedup = env.deduplication is None
        self.noprio = noprio

        self.cp_compile: str = self.prop("cp_compile")
        self.cp_test: str = self.prop("cp_test")
        self.tp_src: str = self.prop("tp_src")
        self.tp_test: str = self.prop("tp_test")
        self.sp_src: str = self.prop("sp_src")
        self.sp_test: str = self.prop("sp_test")
        self.tests_all: List[str] = self.prop("tests_all_class")
        self.tests_trigger: List[str] = self.prop("tests_trigger")
        self.lang_level: int = self.prop("lang_level")

        self.fixup_if_needed()
        self.compile_target_cmdline = self._build_compile_target_cmdline()

        self.test_didnt_touch_target: Dict[Tuple[str, str], bool] = {}
        self.marker_install_possible = True

        self.test_timeout_map = {f'{clz}::{mtd}': timeout for clz, mtd, timeout in self.env.applicable_tests}

    def apply_patch(self, patch_id: int):
        logging.debug('apply patch: %d / %d', patch_id, len(self.config.patches))

        assert 0<patch_id<=len(self.config.patches)

        if USE_TOUCH_MARKER:
            ok, src = add_touch_marker(
                self.config.context_above,
                self.config.patches[patch_id-1],
                self.config.context_below,
            )

            self.marker_install_possible = ok
            with (self.workpath / self.config.filename).open('w') as f:
                f.write(src)

        else:
            self.marker_install_possible = False
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

    def _build_compile_target_cmdline(self):
        lang_level = max(5, self.lang_level)
        javac_cmdline = (
            f'javac'
            f' -J-Duser.language=en'
            f' -nowarn'
            f' -Xmaxerrs 1'
            f' -cp {quote(self.cp_compile)}'
            f' -d {quote(str((self.workpath/self.tp_src).resolve()))}'
            f' -sourcepath {quote(str((self.workpath/self.sp_src).resolve()))}'
            f' -source 1.{lang_level} -target 1.{lang_level}'
            f' {quote(str((self.workpath/self.config.filename).resolve()))}'
        )

        return javac_cmdline

    def compile_interface(self, timeout_sec: Optional[float] = None): # succ, time
        logging.debug('compile patch (interface)')
        return super().compile(timeout_sec=timeout_sec)

    def compile_javac(self, timeout_sec: Optional[float] = None): # succ, time
        logging.debug('compile patch (javac)')
        utils_logger.setLevel(logging.CRITICAL)
        errcode, time_sec, stdout, stderr = run_cmd(self.compile_target_cmdline, timeout_sec=timeout_sec, cwd=self.workdir_s)
        utils_logger.setLevel(logging.CRITICAL)
        return errcode==0, time_sec

    def test(self, test: Optional[str] = None, timeout_sec: Optional[float] = None) -> Tuple[float, List[Tuple[str, str]]]: # tsec, fail_names
        logging.debug('run test: %s', test or '(all)')
        return self.env.interface.test(self.workdir_s, test, timeout_sec=timeout_sec)

    def main(self):  # t_compile, t_run, succlist
        succlist = []

        tot_t_compile = 0
        tot_t_run = 0
        all_patches_failed_mark = False

        marker_path = self.workpath / MARKER_FN

        for n in range(1, 1+len(self.config.patches)):
            cur_status = '?'

            t1 = time.time()
            self.apply_patch(n)
            comp_succ, comp_time_sec = self.compile_javac(timeout_sec=self.COMPILE_TIMEOUT_SEC)
            t2 = time.time()

            tot_t_compile += t2-t1

            if comp_succ:
                t1 = time.time()

                # run individual tests

                for t in self.tests_trigger:
                    test_clz, _, test_mtd = t.partition('::')
                    if self.test_didnt_touch_target.get((test_clz, test_mtd), False): # a globally passed test
                        continue

                    test_str = f'{test_clz}::{test_mtd}'

                    if self.marker_install_possible and marker_path.exists():
                        marker_path.unlink()

                    # XXX: d4j is way too slow to init, give it 2s more time
                    timeout = 2 + self.test_timeout_map.get(test_str, self.RUN_ALL_TEST_TIMEOUT_SEC)
                    try:
                        test_time_sec, fails = self.test(test_str, timeout_sec=timeout)
                        failcnt = len(fails)
                    except Exception: # maybe timeout
                        cur_status = 'T'
                        break

                    logging.debug('test failcnt = %d', failcnt)

                    if self.marker_install_possible:
                        mark_touched = marker_path.exists()

                        if not mark_touched:
                            if failcnt>0: # a globally failed test. stop validating other patches.
                                logging.debug('touch marker NOT FOUND: globally failed')
                                all_patches_failed_mark = True
                                break
                            else: # a globally passed test
                                logging.debug('touch marker NOT FOUND: globally passed')
                                self.test_didnt_touch_target[(test_clz, test_mtd)] = True
                        else:
                            logging.debug('touch marker found')

                    if failcnt>0:
                        cur_status = 'F'
                        break

                else: # did not fail any test
                    # run all tests

                    try:
                        test_time_sec, fails = self.test(None, timeout_sec=self.RUN_ALL_TEST_TIMEOUT_SEC)
                    except Exception: # maybe timeout
                        cur_status = 'T'
                    else:
                        cur_status = 's' if len(fails)==0 else 'F'

                t2 = time.time()

                tot_t_run += t2-t1

                if all_patches_failed_mark:
                    while len(succlist)<len(self.config.patches):
                        succlist.append('X')
                    break

            else:
                cur_status = 'C'
                logging.debug('FAILED to compile')

            succlist.append(cur_status)

        assert len(succlist)==len(self.config.patches)

        return tot_t_compile, tot_t_run, ''.join(succlist)