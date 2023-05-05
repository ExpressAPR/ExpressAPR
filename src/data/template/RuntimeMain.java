package expressapr.testkit;

import org.junit.runner.JUnitCore;
import org.junit.runner.Request;
import org.junit.runner.Result;
import junit.framework.TestCase;
import org.junit.runner.notification.Failure;

import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;
import java.io.*;
import java.util.*;
import java.util.concurrent.*;

import java.edu.columbia.cs.psl.vmvm.runtime.Reinitializer;

public class Main {
    JUnitCore core = new JUnitCore();
    TestKitOrchestrator orchestrator = TestKitOrchestrator.v();

    int PATCHES;
    TestResult[] test_results;
    boolean[] tree_handleable;

    boolean all_patches_killed = false;
    boolean use_test_sel = false;

    int TELEMETRY_actual_count = 0;
    int TELEMETRY_tree_save_count = 0;
    int TELEMETRY_tree_nontrival_cases = 0;
    int TELEMETRY_sel_save_count = 0;

    long TELEMETRY_total_schemata_time_nano = 0;
    long TELEMETRY_total_user_time_nano = 0;
    long TELEMETRY_total_test_time_nano = 0;

    public void the_main(String[] args) throws IOException {
        long start_time = System.currentTimeMillis();

        RuntimeConfig cfg = RuntimeConfig.load("_expapr_patch_config.ser");
        PATCHES = cfg.patch_count;
        tree_handleable = cfg.tree_handleable;
        use_test_sel = cfg.use_test_sel;

        [[[--]]] System.out.printf("got %d tests\n", cfg.tests.length);

        test_results = new TestResult[PATCHES+1];
        for(int i=1; i<=PATCHES; i++)
            test_results[i] = TestResult.Expanding;

        long test_start_time = System.currentTimeMillis();

        for(int tidx=0; tidx<cfg.tests.length; tidx++) {
            RuntimeConfig.TestConfig test_cfg = cfg.get_test(tidx);
            Test test = new Test(test_cfg.clazzname, test_cfg.method);

            [[[--]]] System.out.printf("** [%d] TEST %s :: %s (timeout=%d)\n", tidx, test.get_clazzname(), test.get_method(), test_cfg.timeout_s);
            run_test(test, test_cfg.timeout_s);

            if(all_patches_killed)
                break;
        }

        long stop_time = System.currentTimeMillis();

        System.out.println("RUNTEST DONE! ==");

        for(int i=1; i<=PATCHES; i++) {
            if(test_results[i]==TestResult.Expanding) // not killed by any test
                test_results[i] = TestResult.Passed;
        }
        print_test_result();

        System.out.print("Time: ");
        System.out.println(stop_time-start_time);
        System.out.printf(
            "Telemetry: %d %d %d %d %d %d %d %d %d\n",
            TELEMETRY_actual_count, TELEMETRY_tree_save_count, TELEMETRY_sel_save_count,
            TELEMETRY_total_schemata_time_nano, TELEMETRY_total_user_time_nano,
            stop_time-test_start_time, test_start_time-start_time,
            TELEMETRY_total_test_time_nano,
            TELEMETRY_tree_nontrival_cases
        );
    }

    void print_test_result() {
        System.out.print("patch status: ");
        for(int i=1; i<=PATCHES; i++) {
            System.out.print(test_results[i]==TestResult.Passed ? "s" : "F");
        }
        System.out.print("\n");
    }

    void run_test(Test test, int timeout_s) {
        assert test.tree.get_subtree_expanding_count()==1; // tree should have single root node in expanding status

        // gen tree patches
        boolean some_patch_not_killed = false;
        for(int pid=1; pid<=PATCHES; pid++) {
            if(test_results[pid]==TestResult.Expanding) {
                some_patch_not_killed = true;
                if(tree_handleable[pid])
                    test.tree.add_into_patches(pid);
            }
        }
        if(!some_patch_not_killed) {
            all_patches_killed = true;
            return;
        }

        boolean fallback_to_seq = false;
        [[[--]]] boolean contains_failure = false;

        if(test.tree.get_patches().size()>0) {
            // run tree patches
            while(test.tree.get_subtree_expanding_count()>0) {
                [[[--]]] int expanding_count = test.tree.get_subtree_expanding_count();
                [[[--]]] System.out.printf("invoking tree run (expanding count: %d)\n", expanding_count);
                [[[--]]] TELEMETRY_actual_count++;

                markVmvmReinit();
                orchestrator = TestKitOrchestrator.v();

                orchestrator.mark_tree_run(test.tree);
                orchestrator.begin_tree_run();

                TestResult tr = run_real_test[[[<!--]]]_timed[[[-->]]](test, timeout_s);
                [[[--]]] if(tr==TestResult.Failed) contains_failure = true;

                orchestrator.end_tree_run(tr);

                [[[--]]] TELEMETRY_total_schemata_time_nano += orchestrator.TELEMETRY_total_schemata_time_nano;
                [[[--]]] TELEMETRY_total_user_time_nano += orchestrator.TELEMETRY_total_user_time_nano;

                if(orchestrator.get_fatal()!=null) {
                    [[[--]]] System.out.printf("FATAL: %s\n", orchestrator.get_fatal());
                    fallback_to_seq = true;
                    break;
                }
            }

            if(!fallback_to_seq) {
                [[[--]]] if(contains_failure) print_verbose_tree(test.tree, 0, "init");

                [[[--]]] int old_cnt = TELEMETRY_tree_save_count;

                // collect tree results
                int nonleaf_nodes = collect_tree_result_recursive(test.tree);
                [[[--]]] if(nonleaf_nodes>1) TELEMETRY_tree_nontrival_cases++;

                [[[<!--]]]
                if(test.tree.get_result()!=TestResult.InvokeExpanded) { // revert count, because tree ends at root node
                    int diff = TELEMETRY_tree_save_count - old_cnt;
                    TELEMETRY_tree_save_count = old_cnt;
                    TELEMETRY_sel_save_count += diff;
                }
                [[[-->]]]
            }
        }

        TestResult root_result = fallback_to_seq ? TestResult.Expanding : test.tree.get_result();

        // process patches not handled by tree
        for(int pid=1; pid<=PATCHES; pid++) {
            if(tree_handleable[pid] && !fallback_to_seq) // covered by tree
                continue;
            if(test_results[pid]==TestResult.Failed) // killed by prev test
                continue;
    
            // root_result will be Expanding if all patches have been failed on previous tests
            if(use_test_sel && !(root_result==TestResult.InvokeExpanded || root_result==TestResult.Expanding)) {
                [[[--]]] System.out.printf("skipped single run because root state is %s\n", root_result);
                [[[--]]] TELEMETRY_sel_save_count++;

                if(root_result==TestResult.Failed)
                    test_results[pid] = root_result;

                continue;
            }

            [[[--]]] System.out.printf("invoking single run for patch #%d\n", pid);
            [[[--]]] TELEMETRY_actual_count++;

            markVmvmReinit();
            orchestrator = TestKitOrchestrator.v();

            orchestrator.mark_single_run(pid);
            orchestrator.begin_single_run();

            TestResult tr = run_real_test[[[<!--]]]_timed[[[-->]]](test, timeout_s);

            [[[--]]] TELEMETRY_total_schemata_time_nano += orchestrator.TELEMETRY_total_schemata_time_nano;
            [[[--]]] TELEMETRY_total_user_time_nano += orchestrator.TELEMETRY_total_user_time_nano;

            if(tr==TestResult.Failed)
                test_results[pid] = tr;

            if(!orchestrator.single_run_touched)
                root_result = tr;
        }
    }

    void markVmvmReinit() {
        // in some mockito projects we get a NullPointerException in the LinkedList iterator stuff.
        // have no idea why it happens, may be a weird race. just ignore it for now.
        try {
            Reinitializer.markAllClassesForReinit();
        } catch(NullPointerException e) {
            System.out.println("!! vmvm failed");

            try {
                Reinitializer.markAllClassesForReinit();
            } catch(NullPointerException e2) {
                System.out.println("!! vmvm failed again");
            }
        }
    }

    int collect_tree_result_recursive(DecisionTree node) { // return nums of non-leaf nodes
        TestResult tr = node.get_result();
        if(tr==TestResult.Failed) {
            for(int pid: node.get_patches()) {
                assert test_results[pid]==TestResult.Expanding;
                [[[--]]] System.out.printf("marking patch #%d as failed\n", pid);

                test_results[pid] = TestResult.Failed;
            }
            assert node.get_patches().size()>0 : "wtf node has empty patch set";
            [[[--]]] TELEMETRY_tree_save_count += node.get_patches().size()-1;

            return 0;
        } else if(tr==TestResult.InvokeExpanded) {
            int ret = 1;
            for(Map.Entry<InvokeDetails, DecisionTree> edge: node.get_childs())
                ret += collect_tree_result_recursive(edge.getValue());
            return ret;
        } else {
            assert tr!=TestResult.Expanding; // expecting no expanding node as the tree is fully expanded

            // a passed node
            assert node.get_patches().size()>0 : "wtf node has empty patch set";
            [[[--]]] TELEMETRY_tree_save_count += node.get_patches().size()-1;

            return 0;
        }
    }

    TestResult run_real_test(final Test test, long timeout_sec) {
        class TestTask implements Callable<Result> {
            @Override
            public Result call() {
                return core.run(Request.method(test.get_clazz(), test.get_method()));
            }
        }

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<Result> future = executor.submit(new TestTask());

        try {
            Result result = future.get(timeout_sec, TimeUnit.SECONDS);

            TestResult ret;

            if(!result.wasSuccessful()) {
                [[[<!--]]] System.out.print("> failed ");
                for(Failure f: result.getFailures()) {
                    System.out.print("{");
                    try {
                        System.out.print(f);
                    } catch(StackOverflowError _e) {
                        System.out.print("(stack overflow in toString)");
                    }
                    System.out.print("} ");
                }
                [[[-->]]]

                ret = TestResult.Failed;
            } else {
                [[[--]]] System.out.print("> passed ");

                ret = TestResult.Passed;
            }
            [[[--]]] System.out.println("");

            return ret;
        } catch (ExecutionException e) {
            e.printStackTrace();
            return TestResult.Failed;
        } catch (InterruptedException e) {
            System.out.println("! test interrupted");
            future.cancel(true);
            return TestResult.Failed;
        } catch (TimeoutException e) {
            System.out.println("! test timeout");
            future.cancel(true);
            return TestResult.Failed;
        }
    }

    TestResult run_real_test_timed(final Test test, long timeout_sec) {
        long begin_ts = java.lang.System.nanoTime();
        TestResult r = run_real_test(test, timeout_sec);
        long end_ts = java.lang.System.nanoTime();
        TELEMETRY_total_test_time_nano += end_ts-begin_ts;
        return r;
    }

    void print_verbose_tree(DecisionTree node, int indent, String edge_in_desc) {
        System.out.print('|');
        for(int i=0; i<indent; i++)
            System.out.print("  ");
        if(indent>20) {
            System.out.printf("...  (patch#: %s)\n", node.get_patches().toString());
            return;
        }
        System.out.print("= ");
        switch(node.get_result()) {
            case Expanding:
                System.out.print("EXPD ");
                break;
            case InvokeExpanded:
                System.out.print("CALL ");
                break;
            case Passed:
                System.out.print("SUCC ");
                break;
            case Failed:
                System.out.print("FAIL ");
                break;
        }
        System.out.printf("(%s)\n", edge_in_desc);

        for(Map.Entry<InvokeDetails, DecisionTree> edge: node.get_childs()) {
            StringBuilder desc = new StringBuilder();
            desc.append(edge.getKey().get_res().toString());
            desc.append(" ");
            desc.append(edge.getKey().get_fields_changed().toString());
            print_verbose_tree(edge.getValue(), indent+1, desc.toString());
        }

        if(node.get_childs().isEmpty()) {
            System.out.print('|');
            for(int i=0; i<indent; i++)
                System.out.print("  ");
            System.out.printf("  (patch#: %s)\n", node.get_patches().toString());
        }
    }

    // be careful that all static fields are fucked by vmvm
    public static void main(String[] args) throws IOException {
        Main m = new Main();
        try {
            m.the_main(args);
        } catch(Throwable t) {
            System.out.println("! unexpected error");
            try {
                t.printStackTrace();
            } catch(Throwable _t) {
                System.out.println("! print stack trace failed");
            }
            System.exit(1);
        }
        System.exit(0); // the program will hang if not manually exited. idk why but just leave this workaround here.
    }
}