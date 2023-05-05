package expressapr.testkit;

import java.util.Objects;

enum ExecResultType {
    Running, Finish, Return, ThrowUnchecked, Break, Continue
}

public class TestKitExecResult {
    private ExecResultType type;
    private Object retval;
    private Object retval_for_comparison;

    public TestKitExecResult() {
        set_running();
    }
    public TestKitExecResult clone() {
        TestKitExecResult ret = new TestKitExecResult();
        ret.type = type;
        ret.retval = retval;
        ret.retval_for_comparison = retval_for_comparison;
        return ret;
    }

    public void set_running() {
        type = ExecResultType.Running;
        retval_for_comparison = null;
    }

    public void set_return(Object obj) {
        type = ExecResultType.Return;
        retval = obj;
        retval_for_comparison = obj;
    }
    public void set_throw_unchecked(Throwable obj) {
        type = ExecResultType.ThrowUnchecked;
        retval = obj;
        retval_for_comparison = obj.getClass().getTypeName()+": "+obj.toString();
    }
    public void set_finish() {
        type = ExecResultType.Finish;
        retval_for_comparison = null;
    }
    public void set_break() {
        type = ExecResultType.Break;
        retval_for_comparison = null;
    }
    public void set_continue() {
        type = ExecResultType.Continue;
        retval_for_comparison = null;
    }

    public boolean is_running() {
        return type==ExecResultType.Running;
    }
    public boolean is_return() {
        return type==ExecResultType.Return;
    }
    public boolean is_throw_unchecked() {
        return type==ExecResultType.ThrowUnchecked;
    }
    public boolean is_break() {
        return type==ExecResultType.Break;
    }
    public boolean is_continue() {
        return type==ExecResultType.Continue;
    }
    public Object get_retval() {
        return retval;
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        TestKitExecResult that = (TestKitExecResult) o;
        return type == that.type && Objects.equals(retval_for_comparison, that.retval_for_comparison);
    }

    @Override
    public int hashCode() {
        return Objects.hash(type, retval_for_comparison);
    }

    @Override
    public String toString() {
        if(is_return())
            return "ExecResult{"+ type + " " + retval_for_comparison + '}';
        else if(is_throw_unchecked())
            return "ExecResult{"+ type + " " + retval_for_comparison + '}';
        else
            return "ExecResult{"+ type + '}';
    }
}
