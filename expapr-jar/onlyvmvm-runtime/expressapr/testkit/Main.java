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

//*

import java.edu.columbia.cs.psl.vmvm.runtime.Reinitializer;

class TheMain {
    final static int SINGLE_TEST_TIMEOUT = 60;

    JUnitCore core = new JUnitCore();

    final Class<?>[] TEST_CLASSES = {
        [[[TEST_CLASSES]]]
    };
    ArrayList<Test> TESTS;

    public void main(String[] args) {
        final int N_TEST_RUNS = 2;

        get_all_tests();

        int tidx = -1;
        outer: for(Test test: TESTS) {
            tidx++;
            System.out.printf("** [%d] TEST %s :: %s\n", tidx, test.get_clazz().getCanonicalName(), test.get_method());

            for(int r=0; r<N_TEST_RUNS; r++) {
                TestResult tr = run_test(test);

                if(tr==TestResult.Failed) {
                    test.failed = true;
                    continue outer;
                }
            }
        }

        // also check again in both orders

        System.out.println("** re-check 1");

        for(int i=TESTS.size()-1; i>=0; i--) {
            Test test = TESTS.get(i);
            if(test.failed)
                continue;

            TestResult tr = run_test(test);

            if(tr==TestResult.Failed)
                test.failed = true;
        }

        System.out.println("** re-check 2");

        for(int i=0; i<TESTS.size(); i++) {
            Test test = TESTS.get(i);
            if(test.failed)
                continue;

            TestResult tr = run_test(test);

            if(tr==TestResult.Failed)
                test.failed = true;
        }

        System.out.println("RUNTEST DONE! ==");

        for(Test test: TESTS) {
            if(test.failed)
                System.out.printf("%s::%s::SKIP\n", test.get_clazz().getCanonicalName(), test.get_method());
            else
                System.out.printf("%s::%s::%.3f\n", test.get_clazz().getCanonicalName(), test.get_method(), test.time_s/(N_TEST_RUNS+2));
        }

        System.exit(0);
    }
    
    boolean is_test_buggy(String cls, String method) {
        return (
            false

            // always caught in init self-check
            //|| (
            //    (cls.equals("org.apache.commons.lang3.ClassUtilsTest") || cls.equals("org.apache.commons.lang.ClassUtilsTest"))
            //    && method.equals("testShowJavaBug")
            //) // shows a jvm bug that no longer exists

            || (
            method.toLowerCase().contains("concurren") || cls.toLowerCase().contains("concurren")
            ) // vmvm looks weird in org.apache.commons.lang3.builder.ToStringStyleConcurrencyTest, also we cannot handle unstable tests anyway

            // always caught in init self-check
            //|| (
            //    cls.equals("org.apache.commons.lang.EntitiesPerformanceTest")
            //) // lots of flaky tests because object under test is not initialized across methods

            // always caught in init self-check
            //|| (
            //    cls.equals("org.apache.commons.lang.enums.EnumUtilsTest")
            //) // lots of flaky tests that depends on the fact that ColorEnum is `clinit`ed somewhere else

            // fixed by adding a TZ env var
            //|| (
            //    cls.equals("org.apache.commons.lang.time.DateFormatUtilsTest") && method.equals("testLang312")
            //) // test result depends on the system timezone
        );
    }

    void get_all_tests() {
        TESTS = new ArrayList<Test>();
        for(Class<?> cls: TEST_CLASSES) {
            // https://stackoverflow.com/questions/2635839/junit-confusion-use-extends-testcase-or-test
            boolean is_junit3_testclass = TestCase.class.isAssignableFrom(cls);
            for(Method method: cls.getMethods()) {
                if(
                        is_junit3_testclass ?
                                (method.getName().startsWith("test") && method.getParameterTypes().length==0) :
                                method.isAnnotationPresent(org.junit.Test.class)
                ) {
                    if(!is_test_buggy(cls.getName(), method.getName()))
                        TESTS.add(new Test(cls, method.getName()));
                }
            }
        }
        System.out.print("Got ");
        System.out.print(TESTS.size());
        System.out.println(" tests");
    }

    TestResult run_test(Test test) {
        // in some mockito projects we get a NullPointerException in the LinkedList iterator stuff.
        // have no idea why it happens, may be a weird race. just ignore it for now.
        try {
            Reinitializer.markAllClassesForReinit();
        } catch(NullPointerException e) {
            System.out.println("!! vmvm failed");
            e.printStackTrace();

            try {
                Reinitializer.markAllClassesForReinit();
            } catch(NullPointerException e2) {
                System.out.println("!! vmvm failed again");
                e2.printStackTrace();
            }
        }

        long start_time = System.currentTimeMillis();
        TestResult tr = run_real_test(test);
        long stop_time = System.currentTimeMillis();
        test.time_s += (stop_time-start_time)/1000.0;
        return tr;
    }
    
    static boolean is_junit_result_skipped(Result res) {
        if(res.getFailureCount()==1) {
            try {
                Failure f = res.getFailures().get(0);
                if(f.getMessage()!=null && f.getMessage().contains("No tests found matching Method "))
                    return true;
            } catch(Throwable _t) {
                return false;
            }
        }
        return false;
    }

    TestResult run_real_test(final Test test) {
        class TestTask implements Callable<Result> {
            @Override
            public Result call() {
                return core.run(Request.method(test.get_clazz(), test.get_method()));
            }
        }

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Future<Result> future = executor.submit(new TestTask());

        try {
            Result result = future.get(SINGLE_TEST_TIMEOUT, TimeUnit.SECONDS);

            TestResult ret;

            if(is_junit_result_skipped(result)) {
                System.out.println("> skipped");

                ret = TestResult.Failed; // so it will be skipped during run
            } else if(!result.wasSuccessful()) {
                System.out.print("> failed ");
                for(Failure f: result.getFailures()) {
                    System.out.print("{");
                    try {
                        System.out.print(f.getException().getClass().getCanonicalName());
                        System.out.print(" : ");
                        System.out.print(f);
                        System.out.print(" : ");
                        System.out.print(f.getTrace());
                    } catch(StackOverflowError _e) {
                        System.out.print("(stack overflow in toString)");
                    }
                    System.out.print("} ");
                }
                System.out.println("");

                ret = TestResult.Failed;
            } else {
                //System.out.println("> passed ");

                ret = TestResult.Passed;
            }

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
}
//*/

// because `static` fields will be fucked by vmvm
public class Main {
    public static void main(String[] args) {
        TheMain tm = new TheMain();
        tm.main(args);
    }
}
