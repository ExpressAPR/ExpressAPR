import traceback
from typing import Optional, Tuple, Dict, Type, Any
from pathlib import Path

from ..runtime_env import RuntimeEnv
from ..utils import check_output
from ..patcher import ExpAprPatcher, FallbackPatcher
from ..servant_connector import ServantConnector

class Technique:
    def __init__(self, env: RuntimeEnv, idx0: int, args: Any):
        self.env = env
        self.idx0 = idx0
        self.args = args
        self.proj_path_s = str(env.projects[idx0]['root'])

    def run(self, jsonpath: str) -> Tuple[Optional[str], dict]:
        raise NotImplementedError()

    def shutdown(self):
        pass

class ExpAprTechnique(Technique):
    def __init__(self, env: RuntimeEnv, idx0: int, args: Any):
        super().__init__(env, idx0, args)
        self.con = ServantConnector(
            enable_assertion=False,
            igniter_path=Path('../expapr-jar'),
        )

        dedup = {'type': 'disabled'} if args.no_dedup else env.deduplication
        self.con.request_on_startup({
            'action': 'setup',
            'purity_source': dedup,
        }, 30)

    def run(self, jsonpath: str) -> Tuple[Optional[str], dict]:
        try:
            check_output('git reset EXPAPR_RUNTIME_INJECTED --hard && git clean -d -f', 30, cwd=self.proj_path_s)

            p = ExpAprPatcher(jsonpath, self.env, self.idx0, noprio=self.args.no_prio)
            patchcnt, t_install, t_run, succlist, inst_telemetry_cnts, run_telemetry_cnts = p.main(self.con)

        except Exception as e:
            return None, {
                'expapr_error_type': type(e).__name__,
                'expapr_error_repr': repr(e),
                'expapr_error_trace': traceback.format_exc(),
            }

        else:
            return succlist, {
                't_compile': t_install,
                't_run': t_run,
                'inst_telemetry_cnts': inst_telemetry_cnts,
                'run_telemetry_cnts': run_telemetry_cnts,
            }

    def shutdown(self):
        self.con.shutdown()

class FallbackTechnique(Technique):
    def run(self, jsonpath: str) -> Tuple[Optional[str], dict]:
        try:
            check_output('git reset EXPAPR_INTERFACE_ORIGINAL --hard && git clean -d -f', 30, cwd=self.proj_path_s)

            p = FallbackPatcher(jsonpath, self.env, self.idx0)
            t_compile, t_run, succlist = p.main()

        except Exception as e:
            return None, {
                'fallback_error_type': type(e).__name__,
                'fallback_error_repr': repr(e),
                'fallback_error_trace': traceback.format_exc(),
            }

        else:
            return succlist, {
                't_compile': t_compile,
                't_run': t_run,
            }

TECHNIQUES: Dict[str, Type[Technique]] = {
    'expapr': ExpAprTechnique,
    'fallback': FallbackTechnique,
}