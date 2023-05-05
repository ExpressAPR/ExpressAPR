package expressapr.igniter.purity;

import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.stmt.Statement;
import com.github.javaparser.resolution.UnsolvedSymbolException;
import com.github.javaparser.resolution.declarations.ResolvedMethodDeclaration;
import com.github.javaparser.symbolsolver.JavaSymbolSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.CombinedTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.JavaParserTypeSolver;
import com.github.javaparser.symbolsolver.resolution.typesolvers.ReflectionTypeSolver;
import expressapr.igniter.Args;
import expressapr.igniter.Main;

import java.io.BufferedReader;
import java.io.FileNotFoundException;
import java.io.FileReader;
import java.io.IOException;
import java.util.HashSet;

public class SidefxDbSource extends TrivialPuritySource implements AbstractPuritySource {
    private HashSet<String> impureMethodSet = new HashSet<>();
    private String sidefx_db_path;
    private String src_absolute_path;

    private boolean symbol_solver_initialized;

    public SidefxDbSource(String sidefx_db_path, String src_absolute_path) {
        this.sidefx_db_path = sidefx_db_path;
        this.src_absolute_path = src_absolute_path;
        this.symbol_solver_initialized = false;

        load_sidefx_db();
    }

    public void setSrcPath(String path) {
        src_absolute_path = path;
        symbol_solver_initialized = false;
    }

    @Override
    public void initialize() {
        // src_absolute_path may not be available at constructor, so delay it to here
        if(!symbol_solver_initialized) {
            setup_symbol_solver();
            symbol_solver_initialized = true;
        }
    }

    @Override
    public void initializeForPatches(NodeList<Statement> patches) {
        if(Args.POPULATE_CACHE_FOR_SYMBOL_SOLVER)
            populate_cache_for_symbol_solver(patches);
    }

    @Override
    public boolean isMethodCallPure(MethodCallExpr call) {
        if(super.isMethodCallPure(call)) // check TrivialPuritySource first
            return true;

        try {
            ResolvedMethodDeclaration method = call.resolve();

            String signature = String.format(
                "<%s: %s %s>",
                method.declaringType().getId(),
                method.getReturnType().describe(),
                method.getSignature()
            );

            //System.out.printf("succ resolved sidefx %s -> %s\n", call, signature);

            //noinspection RedundantIfStatement
            if(impureMethodSet.contains(signature)) {
                //List<String> sidefx = methodToModified.get(signature);
                return false;
            } else {
                return true;
            }
        } catch(UnsolvedSymbolException e) {
            //System.out.println(call.toString() + ": sidefx symbol not resolved");
            //e.printStackTrace();
            return false;
        } catch(Exception e) {
            System.out.println(call.toString() + ": sidefx processing error");
            e.printStackTrace();
            return false;
        }
    }

    private void load_sidefx_db() {
        try {
            BufferedReader reader = new BufferedReader(new FileReader(sidefx_db_path));
            String line;
            while ((line = reader.readLine()) != null) {
                String [] items = line.split("\t");
                if(items.length!=2)
                    throw new RuntimeException("invalid line in sidefx db: "+line);

                impureMethodSet.add(items[0]);
                //methodToModified.get(items[0]).add(items[1]);
            }
        } catch (FileNotFoundException e) {
            System.out.println("sidefx db not found!");
            throw new RuntimeException("sidefx db not found: "+sidefx_db_path);
        } catch (IOException e) {
            e.printStackTrace();
            throw new RuntimeException("load sidefx db IOException: "+e);
        }
    }

    private void setup_symbol_solver() {
        //long ts1 = System.nanoTime();

        CombinedTypeSolver solver = new CombinedTypeSolver();
        solver.add(new ReflectionTypeSolver());
        if(src_absolute_path!=null)
            solver.add(new JavaParserTypeSolver(src_absolute_path));
        else
            System.out.println("sidefx db source: src path not specified, skipped analysis for src code");

        JavaSymbolSolver symbolSolver = new JavaSymbolSolver(solver);
        StaticJavaParser.getConfiguration().setSymbolResolver(symbolSolver);

        //long ts2 = System.nanoTime();

        //Main.total_offline_time_ns += ts2-ts1;
    }

    /**
     * JavaSymbolSolver requires nontrivial setup time (about 1 sec or so for each cluster) reading the whole code base.
     * While this can be done offline (the value can be cached), I am lazy to modify it to do so.
     * Therefore, we just measure the setup time and exclude it in our final timing.
     */
    private void populate_cache_for_symbol_solver(NodeList<Statement> patches) {
        //long ts1 = System.nanoTime();

        /*
        // TMP: collect method calls
        FileWriter fw_;
        try {
            fw_ = new FileWriter("_method_calls", true);
        } catch (IOException e) {
            fw_ = null;
            e.printStackTrace();
        }
        FileWriter fw = fw_;
         */

        int pidx = 0;
        for(Statement patch_block: patches) {
            pidx++;
            System.out.printf("solve symbol for patch #%d\n", pidx);

            assert patch_block instanceof BlockStmt;

            for(Statement stmt: ((BlockStmt)patch_block).getStatements()) {
                stmt.walk(MethodCallExpr.class, (call)->{
                    try {
                        ResolvedMethodDeclaration method = call.resolve();

                        String signature = String.format(
                            "<%s: %s %s>",
                            method.declaringType().getId(),
                            method.getReturnType().describe(),
                            method.getSignature()
                        );

                        /*
                        // TMP: collect method calls
                        if(fw!=null) {
                            fw.write(sidefx_db_path+"\t"+signature+"\n");
                        }
                         */

                        System.out.printf("  - %s\n", signature);
                    } catch(Exception ignored) {}
                });
            }
        }

        /*
        // TMP: collect method calls
        if(fw!=null) {
            try {
                fw.close();
            } catch (IOException e) {
                e.printStackTrace();
            }
        }
         */

        //long ts2 = System.nanoTime();

        //Main.total_offline_time_ns += ts2-ts1;
    }
}
