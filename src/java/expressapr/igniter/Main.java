package expressapr.igniter;

import expressapr.igniter.purity.AbstractPuritySource;
import expressapr.testkit.RuntimeConfig;

import java.io.*;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.List;
import java.util.Objects;

public class Main {
    String patches_json_fn = "";
    String project_root_path = "";
    String project_src_path = "";
    String project_test_path = "";
    String project_vendor_path = "testkit_lib";
    String javac_cmdline = "";
    List<String> related_test_classes;
    List<String> all_tests;

    public static long total_offline_time_ns = 0;

    static final String[] COPY_RUNTIME_CLASSNAMES = {
        "DecisionTree",
        "InvokeDetails",
        "RuntimeConfig",
        "Test",
        "TestKitExecResult",
        "TestKitOrchestrator",
        "TestResult",
        "internal_exceptions/PatchBreak",
        "internal_exceptions/PatchContinue",
        "internal_exceptions/PatchFinish",
    };

    Main(
        String patches_json_fn,
        String project_root_path,
        String project_src_path,
        String project_test_path,
        String javac_cmdline,
        AbstractPuritySource purity_source,
        List<String> all_tests
    ) throws IOException {
        this.patches_json_fn = patches_json_fn;
        this.project_root_path = project_root_path;
        this.project_src_path = project_src_path;
        this.project_test_path = project_test_path;
        this.javac_cmdline = javac_cmdline;
        this.all_tests = all_tests;

        assert project_src_path.charAt(0)!='/' : "src path should be relative to project root path";
        assert project_test_path.charAt(0)!='/' : "test path should be relative to project root path";

        SideEffectAnalyzer.purity_source = purity_source;

        if(Args.RUNTIME_DEBUG)
            System.out.println("!!! RUNTIME_DEBUG is on, performance is not guaranteed");
    }

    public void copyRuntimeFiles() throws IOException {
        // copy runtime files to both src dir and test dir,
        // otherwise some runtime `.class`es not used in src may not be generated in `compile` phase,
        // causing an exception in `compile-tests` phase

        Files.createDirectories(Paths.get(project_root_path+"/"+project_src_path+"/expressapr/testkit"));
        Files.createDirectories(Paths.get(project_root_path+"/"+project_src_path+"/expressapr/testkit/internal_exceptions"));
        Files.createDirectories(Paths.get(project_root_path+"/"+project_test_path+"/expressapr/testkit"));
        Files.createDirectories(Paths.get(project_root_path+"/"+project_test_path+"/expressapr/testkit/internal_exceptions"));

        for(String fn: COPY_RUNTIME_CLASSNAMES) {
            Files.copy(
                Paths.get("data/runtime-class/"+fn+".java"),
                Paths.get(project_root_path+"/"+project_src_path+"/expressapr/testkit/"+fn+".java"),
                StandardCopyOption.REPLACE_EXISTING
            );

            Files.copy(
                Paths.get("data/runtime-class/"+fn+".java"),
                Paths.get(project_root_path+"/"+project_test_path+"/expressapr/testkit/"+fn+".java"),
                StandardCopyOption.REPLACE_EXISTING
            );
        }
    }

    public void copyVendorFiles() throws IOException {
        Files.createDirectories(Paths.get(project_root_path+"/"+project_vendor_path));

        File jars = new File("data/runtime-vendor");
        for(File file: Objects.requireNonNull(jars.listFiles())) {
            Files.copy(
                file.toPath(),
                Paths.get(project_root_path+"/"+project_vendor_path+"/"+file.getName()),
                StandardCopyOption.REPLACE_EXISTING
            );
        }
    }

    public PatchVerifier generatePatchedClass() throws IOException {
        PatchVerifier v = new PatchVerifier(patches_json_fn, project_root_path, javac_cmdline);

        if(v.orig_patch_count>0)
            v.verifyAllAndWriteFile();

        System.out.printf("== got %d compiled patch\n", v.compiled_patch_count);
        //assert v.compiled_patch_count>=0 : "verifier reports error"; // used for debugging, remove that in production
        return v;
    }

    public void genRuntimeMain(PatchVerifier v) throws IOException {
        Files.createDirectories(Paths.get(project_root_path+"/"+project_test_path+"/expressapr/testkit"));
        FileWriter writer = new FileWriter(project_root_path+"/"+project_test_path+"/expressapr/testkit/Main.java");

        writer.write(
            StringTemplate.fromTemplateName("RuntimeMain")
                .doneWithNewline()
        );
        writer.close();
    }

    public void genRuntimeConfig(PatchVerifier v) throws IOException {
        RuntimeConfig cfg = new RuntimeConfig(all_tests.size(), v.compiled_patch_count);
        cfg.use_test_sel = SideEffectAnalyzer.purity_source!=null || Args.TEST_SEL_WHEN_NODEDUP;

        for(int i=0; i<all_tests.size(); i++) {
            String[] t = all_tests.get(i).split("::");
            assert t.length==3 : "test name should be in format `clazz::method::timeout_s`";
            cfg.tests[i] = new RuntimeConfig.TestConfig(t[0], t[1], Integer.parseInt(t[2]));
        }

        if(v.trans.tree_handleable!=null) {
            assert v.trans.tree_handleable.size()==cfg.patch_count;

            for(int i=0; i<v.trans.tree_handleable.size(); i++)
                cfg.tree_handleable[i+1] = v.trans.tree_handleable.get(i);
        }

        cfg.dump(project_root_path+"/_expapr_patch_config.ser");
    }
}
