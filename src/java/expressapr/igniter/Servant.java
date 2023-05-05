package expressapr.igniter;

import expressapr.igniter.purity.AbstractPuritySource;
import expressapr.igniter.purity.SidefxDbSource;
import expressapr.igniter.purity.TrivialPuritySource;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.PrintWriter;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

public class Servant {
    final static String SERVANT_BANNER = "SERVANT_RPC_V2";

    private static AbstractPuritySource puritySource;

    static List<String> getJsonListString(JSONArray arr) {
        List<String> ret = new ArrayList<>();
        for (int i = 0; i < arr.length(); i++) {
            ret.add(arr.getString(i));
        }
        return ret;
    }

    static void setupFlags(JSONObject flags) {
        Args.RUNTIME_DEBUG = flags.getBoolean("runtime_debug");
        Args.TEST_SEL_WHEN_NODEDUP = flags.getBoolean("test_sel_when_nodedup");
        Args.WRITE_COMPILER_MSG = flags.getBoolean("write_compiler_msg");
    }

    static void setupPuritySource(JSONObject config) {
        String type = config.getString("type");
        switch(type) {
            case "disabled":
                puritySource = null;
                break;

            case "trivial":
                puritySource = new TrivialPuritySource();
                break;

            case "sidefx_db":
                puritySource = new SidefxDbSource(
                    config.getString("sidefx_db_path"),
                    null
                );
                break;
        }
    }

    static JSONObject respond(JSONObject req) throws IOException {
        String action = req.getString("action");

        if(action.equals("setup")) {
            setupPuritySource(req.getJSONObject("purity_source"));
            return new JSONObject();
        }

        if(puritySource instanceof SidefxDbSource) {
            String path = req.getString("project_root_path") + "/" + req.getString("project_src_path");
            ((SidefxDbSource) puritySource).setSrcPath(path);
        }

        Main.total_offline_time_ns = 0;
        Main main = new Main(
            req.getString("patches_json_fn"),
            req.getString("project_root_path"),
            req.getString("project_src_path"),
            req.getString("project_test_path"),
            req.getString("javac_cmdline"),
            puritySource,
            getJsonListString(req.getJSONArray("all_tests"))
        );

        setupFlags(req.getJSONObject("flags"));
        PatchVerifier v;

        switch(action) {
            case "run":
                v = main.generatePatchedClass();
                main.genRuntimeConfig(v);
                break;

            case "init":
                main.copyRuntimeFiles();
                main.copyVendorFiles();
                v = main.generatePatchedClass();
                main.genRuntimeMain(v);
                break;

            default:
                throw new RuntimeException("unknown action: " + action);
        }

        assert v!=null;

        int tree_handleable_cnt = 0;
        if(v.trans.tree_handleable!=null) {
            for(boolean h: v.trans.tree_handleable)
                if(h)
                    tree_handleable_cnt++;
        }

        return new JSONObject()
            .put("compiled_patch_count", v.compiled_patch_count)
            .put("status_line", v.getStatusLine())
            .put("telemetry_cnts", Arrays.asList(
                tree_handleable_cnt,
                Main.total_offline_time_ns
            ));
    }

    @SuppressWarnings({"InfiniteLoopStatement", "resource"})
    public static void main(String[] args) throws IOException {
        int port = Integer.parseInt(args[0]);
        String nonce = args[1];
        Socket sock = new Socket("127.0.0.1", port);
        sock.setTcpNoDelay(true);

        BufferedReader reader = new BufferedReader(
            new java.io.InputStreamReader(
                sock.getInputStream()
            )
        );

        PrintWriter writer = new PrintWriter(sock.getOutputStream(), true);

        writer.println(SERVANT_BANNER);
        writer.println(nonce);
        System.out.printf("servant connected to %d, waiting for request\n", sock.getPort());

        while(true) {
            String req_line = reader.readLine();
            JSONObject req = new JSONObject(req_line);

            String res_line;
            try {
                JSONObject res = respond(req);
                res_line = res.toString();
                assert !res_line.contains("\n") : "json res should not contain line breaks";
            } catch(Exception e) {
                e.printStackTrace();
                writer.println("FAIL");
                writer.println(
                    new JSONObject()
                        .put("message", e.toString())
                        .put("stacktrace", e.getStackTrace())
                        .toString()
                );
                continue;
            }

            writer.println("succ");
            writer.println(res_line);
        }
    }
}
