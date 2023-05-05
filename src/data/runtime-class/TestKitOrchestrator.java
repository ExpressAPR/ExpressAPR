package expressapr.testkit;

import java.util.ArrayList;
import java.util.Map;
import java.util.Set;
import sun.misc.Unsafe;
import java.lang.reflect.Field;

public class TestKitOrchestrator {
    static TestKitOrchestrator singleton = null;
    public static TestKitOrchestrator v() {
        if(singleton==null)
            singleton = new TestKitOrchestrator();
        return singleton;
    }

    private int single_patch_id; // valid when single_run
    private DecisionTree current_node;
    private InvokeDetails current_invoke;

    public boolean single_run_touched;
    public long TELEMETRY_total_schemata_time_nano;
    public long TELEMETRY_total_user_time_nano;

    private Long thread_id; // for sancheck
    private String fatal_error;

    public TestKitOrchestrator() {}

    public boolean is_tree_run() {
        return current_node!=null;
    }
    public int get_patch_id() {
        assert !is_tree_run();
        return single_patch_id;
    }
    public ArrayList<Integer> get_patches() {
        assert is_tree_run();
        return current_node.get_patches();
    }
    public TestResult get_tree_result() {
        assert is_tree_run();
        return current_node.get_result();
    }

    public void mark_single_run(int patch_id) {
        current_node = null;
        this.single_patch_id = patch_id;
    }
    public void mark_tree_run(DecisionTree dt) {
        assert dt!=null;
        current_node = dt;
    }

    public void begin_tree_run() {
        assert current_invoke==null;
        assert is_tree_run();

        thread_id = null;
        fatal_error = null;
        TELEMETRY_total_schemata_time_nano = 0;
        TELEMETRY_total_user_time_nano = 0;
    }
    public void end_tree_run(TestResult tr) {
        assert tr==TestResult.Passed || tr==TestResult.Failed;

        if(get_tree_result()!=TestResult.Expanding) {
            // do not call `report_fatal` because this code runs outside of JUnit
            fatal_error = "unstable test: stopped on non-leaf node, tree result is "+get_tree_result().toString();
            return;
        }

        current_node.set_result(tr);
    }

    public void begin_single_run() {
        single_run_touched = false;
        TELEMETRY_total_schemata_time_nano = 0;
        TELEMETRY_total_user_time_nano = 0;
    }

    public void report_before_invoke() {
        //System.out.println("stub before");

        assert current_invoke==null;
        assert is_tree_run();

        current_invoke = new InvokeDetails();
    }

    public void report_field_before(String name, Object value) {
        assert current_invoke!=null;
        current_invoke.report_field_before(name, value);
    }
    public Object report_field_after_Object(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_Object(name, value);
    }
    public Object report_field_after_byte(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_byte(name, value);
    }
    public Object report_field_after_short(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_short(name, value);
    }
    public Object report_field_after_int(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_int(name, value);
    }
    public Object report_field_after_long(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_long(name, value);
    }
    public Object report_field_after_float(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_float(name, value);
    }
    public Object report_field_after_double(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_double(name, value);
    }
    public Object report_field_after_boolean(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_boolean(name, value);
    }
    public Object report_field_after_char(String name, Object value) {
        assert current_invoke!=null;
        return current_invoke.report_field_after_char(name, value);
    }

    public void report_after_invoke(TestKitExecResult res, int patchid) {
        //System.out.println("stub after");

        assert current_invoke!=null;
        assert is_tree_run();

        TestKitExecResult changed_res = res.clone();

        current_invoke.report_exec_result(changed_res);
        current_node.get_or_insert_child(current_invoke, TestResult.Expanding, patchid);
        current_invoke = null;
    }

    public void finish_expanding() {
        assert current_invoke==null;
        assert is_tree_run();
        assert current_node.get_result()==TestResult.Expanding;

        current_node.set_result(TestResult.InvokeExpanded);
    }

    public void report_fatal(String err) {
        System.out.println("!! TESTKIT REPORT FATAL: "+err);
        fatal_error = err;
        //fail("FATAL TESTKIT ERROR"); // cause compile error because junit is not present in src scope
        throw new Error("FATAL TESTKIT ERROR: "+err);
    }
    public String get_fatal() {
        return fatal_error;
    }

    public Map.Entry<InvokeDetails, DecisionTree> move_to_expandable_edge() {
        assert current_node.get_subtree_expanding_count()>0;
        Set<Map.Entry<InvokeDetails, DecisionTree>> edges = current_node.get_childs();
        for(Map.Entry<InvokeDetails, DecisionTree> edge: edges) {
            if(edge.getValue().get_subtree_expanding_count()>0) {
                current_node = edge.getValue();

                assert current_node.get_patches().size()>0;
                assert current_node.get_result()==TestResult.Expanding || current_node.get_result()!=TestResult.InvokeExpanded;

                return edge;
            }
        }

        // if run to here: no edge is expandable
        report_fatal("internal error: decision tree inconsistent");
        throw new RuntimeException("impossible"); // report_fatal will always throw, add this `throw` to make compiler happy
    }

    public void tree_sancheck() {
        if(current_invoke!=null)
            report_fatal("recursive call in patch");

        long cur_tid = Thread.currentThread().getId();
        if(thread_id==null) {
            thread_id = cur_tid;
        } else if(thread_id!=cur_tid) {
            report_fatal("multithread detected");
        }

        TestResult tr = current_node.get_result();
        if(tr!=expressapr.testkit.TestResult.Expanding && tr!=expressapr.testkit.TestResult.InvokeExpanded)
            report_fatal("unstable test: expanding on leaf node");
    }

    public static Unsafe unsafe;
    static {
        try {
            Field f = Unsafe.class.getDeclaredField("theUnsafe");
            f.setAccessible(true);
            unsafe = (Unsafe) f.get(null);
        } catch (NoSuchFieldException e) {
            throw new RuntimeException("CANNOT GET UNSAFE");
        } catch (IllegalAccessException e) {
            throw new RuntimeException("CANNOT GET UNSAFE");
        }
    }

    public void mark_single_run_touched() {
        single_run_touched = true;
    }
}
