package expressapr.igniter;

import expressapr.igniter.purity.AbstractPuritySource;
import expressapr.igniter.purity.SidefxDbSource;

import java.io.IOException;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class Cli {
    public static void main(String[] args) throws IOException {
        String patches_json_fn = args[0]; //"test-domath/patches.json";
        String project_root_path = args[1]; //"test-domath";
        // args[2] originally test classes, but abandoned
        String project_src_path = args[3]; //"src";
        String project_test_path = args[4]; //"test";
        String javac_cmdline = args[5]; //"javac";
        String dedup_flag = args[6]; //"dedup-on"/"dedup-off";
        String sidefx_db_path = args[7]; //"xxx.csv";
        List<String> all_tests = "".equals(args[8]) ? new ArrayList<>() : Arrays.asList(args[8].split("\\|"));

        AbstractPuritySource puritySource = null;

        if(!dedup_flag.equals("dedup-off")) { // fail fast: if the flag is something else, we set it to on, and it will crash when the sidefx db is not found
            puritySource = new SidefxDbSource(
                sidefx_db_path,
                project_root_path+"/"+project_src_path
            );
        }

        Main.total_offline_time_ns = 0;
        Main main = new Main(
            patches_json_fn,
            project_root_path,
            project_src_path,
            project_test_path,
            javac_cmdline,
            puritySource,
            all_tests
        );

        long start_time_ = System.currentTimeMillis();

        main.copyRuntimeFiles();
        main.copyVendorFiles();
        PatchVerifier v = main.generatePatchedClass();
        main.genRuntimeMain(v);

        long stop_time_ = System.currentTimeMillis();

        // print stats

        System.out.println("PREPROCESS DONE! ==");

        System.out.print("preprocess time (ms): ");
        System.out.println(stop_time_-start_time_);

        System.out.print("patch count left: ");
        System.out.println(v.compiled_patch_count);

        System.out.print("patch status: ");
        System.out.println(v.getStatusLine());

        int tree_handleable_cnt = 0;
        if(v.trans.tree_handleable!=null) {
            for(boolean h: v.trans.tree_handleable)
                if(h)
                    tree_handleable_cnt++;
        }

        System.out.printf("Telemetry: %d %d\n", tree_handleable_cnt, Main.total_offline_time_ns);
    }
}
