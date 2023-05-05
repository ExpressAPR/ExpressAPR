package expressapr.testkit;

import java.io.*;
import java.util.Arrays;
import java.util.Scanner;

public class RuntimeConfig {
    public static class TestConfig {
        public String clazzname;
        public String method;
        public int timeout_s;

        public TestConfig(String clazzname, String method, int timeout_s) {
            this.clazzname = clazzname;
            this.method = method;
            this.timeout_s = timeout_s;
        }
    }

    public TestConfig[] tests;
    public int patch_count;
    public boolean use_test_sel;
    public boolean[] tree_handleable;
    private int test_loadidx_next;
    private Scanner r;

    public RuntimeConfig(int n_tests, int n_patches, Scanner scanner) {
        tests = new TestConfig[n_tests];
        tree_handleable = new boolean[1+n_patches];
        patch_count = n_patches;
        test_loadidx_next = 0;
        r = scanner;
    }
    public RuntimeConfig(int n_tests, int n_patches) {
        this(n_tests, n_patches, null);
        test_loadidx_next = n_tests;
    }

    public void dump(String fn) throws IOException {
        PrintWriter w = new PrintWriter(new BufferedWriter(new FileWriter(fn)));

        w.println(tests.length);
        w.println(patch_count);
        w.println(use_test_sel ? '1' : '0');

        for(boolean b: tree_handleable)
            w.print(b ? '1' : '0');
        w.println();

        for(TestConfig t: tests) {
            w.println(t.clazzname);
            w.println(t.method);
            w.println(t.timeout_s);
        }

        w.println("END");
        w.flush();
        w.close();
    }

    public static RuntimeConfig load(String fn) throws IOException {
        Scanner r = new Scanner(new BufferedReader(new FileReader(fn)));
        r.useDelimiter("\\n");

        int n_tests = r.nextInt();
        int n_patches = r.nextInt();
        boolean use_test_sel = r.nextInt()=='1';
        r.nextLine();

        RuntimeConfig cfg = new RuntimeConfig(n_tests, n_patches, r);
        cfg.use_test_sel = use_test_sel;

        char[] s = r.nextLine().toCharArray();
        for(int i=0; i<=n_patches; i++) // len is 1+n_patches
            cfg.tree_handleable[i] = s[i] == '1';

        return cfg;
    }

    private void load_next_test() {
        assert test_loadidx_next<tests.length;

        String clz = r.nextLine();
        String mtd = r.nextLine();
        int time = r.nextInt();
        r.nextLine();

        tests[test_loadidx_next] = new TestConfig(clz, mtd, time);
        test_loadidx_next++;
    }

    public TestConfig get_test(int idx) throws IOException {
        assert r!=null;

        while(test_loadidx_next<=idx)
            load_next_test();

        return tests[idx];
    }
}
