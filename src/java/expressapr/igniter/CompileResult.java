package expressapr.igniter;

import java.util.ArrayList;
import java.util.List;

public class CompileResult {
    private boolean success;
    private List<Failure> error_lines;

    static class Failure {
        public String fn;
        public int line;
        public String errormsg;

        public Failure(String fn, int line, String errormsg) {
            if(fn.startsWith("/")) // remove prefix /
                fn = fn.substring(1);

            this.fn = fn;
            this.line = line;
            this.errormsg = errormsg.trim();
        }

        public String toString() {
            return fn + ":" + line + ": " + errormsg;
        }
    };

    private CompileResult(boolean succ, List<Failure> error_lines) {
        this.success = succ;
        this.error_lines = error_lines;
    }

    static CompileResult parseCompilerFailure(List<String> stdout, String workdir_abs) {
        ArrayList<Failure> error_lines = new ArrayList<>();
        for(String line: stdout) {
            int err_idx = line.indexOf(": error:");

            if(err_idx!=-1) {
                String errormsg = line.substring(err_idx + ": error:".length());
                int fn_idx = line.indexOf(workdir_abs);

                if(fn_idx!=-1 && fn_idx<err_idx) {
                    String error_pos = line.substring(fn_idx+workdir_abs.length(), err_idx);
                    int line_idx = error_pos.lastIndexOf(':');

                    error_lines.add(new Failure(
                        error_pos.substring(0, line_idx),
                        Integer.parseInt(error_pos.substring(line_idx+1)),
                        errormsg
                    ));
                }
            }
        }

        assert !error_lines.isEmpty() : String.join("\n", stdout);

        return new CompileResult(false, error_lines);
    }
    static CompileResult asSuccess() {
        return new CompileResult(true, null);
    }

    boolean isSuccess() {
        return success;
    }
    List<Failure> getErrorLines() {
        return error_lines;
    }
}
