package expressapr.igniter;

import com.github.javaparser.ParseProblemException;
import com.github.javaparser.StaticJavaParser;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.BlockStmt;
import com.github.javaparser.ast.stmt.IfStmt;
import com.github.javaparser.ast.stmt.ReturnStmt;
import com.github.javaparser.ast.stmt.Statement;
import expressapr.igniter.purity.AbstractPuritySource;

import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;

public class SideEffectAnalyzer {
    public static AbstractPuritySource purity_source = null; // if null: fallback to nodedup mode

    final static String INJECTION_POINT_MARKER = "__TESTKIT_MARKER_SIDEFX";

    private final PreTransformer context;

    SideEffectAnalyzer(PreTransformer context) {
        this.context = context;
    }

    /**
     * Invoked once, before calls to `analyze`.
     * Load offline analysis result if needed.
     */
    public void initialize() {
        if(purity_source==null) {
            System.out.println("sidefx analyzer SKIPPED in nodedup mode");
            return;
        }

        purity_source.initialize();
    }

    private static String titleCase(String s) {
        return s.substring(0, 1).toUpperCase() + s.substring(1);
    }

    private String generateTotalSourceCode() {
        StringBuilder sb = new StringBuilder("\nif("+INJECTION_POINT_MARKER+") {");

        for(List<Statement> patch: context.stmts_patches) {
            sb.append("\n{ /* patch */\n");
            for(Statement stmt: patch) {
                sb.append(TreeStringify.print(stmt));
            }
            sb.append("\n}");
        }

        sb.append("}");

        String src = TreeStringify.print(context.cu);
        return PreTransformer.commentReplace(src, PreTransformer.MARK_CODEGEN_IP_POINT, sb.toString());
    }

    Map<List<Statement>, Integer> patch_to_idx;

    private void calcPatchToIdx() {
        patch_to_idx = new HashMap<>();

        for(int idx=0; idx<context.stmts_patches.size(); idx++)
            patch_to_idx.put(context.stmts_patches.get(idx), idx);
    }

    private boolean mayContainDeepTarget(Expression expr, Map<String, Variable> fields) {
        if(expr instanceof NameExpr)
            return fields.get(((NameExpr)expr).getNameAsString())!=null;
        else if(expr instanceof ArrayAccessExpr)
            return mayContainDeepTarget(((ArrayAccessExpr)expr).getName(), fields);
        else if(expr instanceof EnclosedExpr)
            return mayContainDeepTarget(((EnclosedExpr)expr).getInner(), fields);
        else
            return true;
    }

    List<Set<Variable>> shallow_sidefxs;
    List<Boolean> should_tree_skip;

    public void analyze(Map<String, Variable> fields) {
        shallow_sidefxs = new ArrayList<>();
        should_tree_skip = new ArrayList<>();
        calcPatchToIdx();

        String new_src = generateTotalSourceCode();
        CompilationUnit new_cu = StaticJavaParser.parse(new_src);

        IfStmt node = (IfStmt)(
            new_cu.findFirst(
                NameExpr.class,
                (exp)->INJECTION_POINT_MARKER.equals(exp.getNameAsString())
            ).get().getParentNode().get()
        );
        assert node.getThenStmt() instanceof BlockStmt;
        NodeList<Statement> patches = ((BlockStmt)node.getThenStmt()).getStatements();
        assert patches.size()==context.stmts_patches.size();

        if(purity_source!=null)
            purity_source.initializeForPatches(patches);

        boolean rettype_safe = isTypeSafeForComparison(context.rettype);

        for(Statement patch_block: patches) {
            assert patch_block instanceof BlockStmt;
            Set<Variable> out = new HashSet<>();
            AtomicBoolean tree_skip = new AtomicBoolean(false);

            if(purity_source==null) {
                tree_skip.set(true); // fallback to true
            }

            for(Statement stmt: ((BlockStmt)patch_block).getStatements()) {
                // detect assignment
                stmt.walk(AssignExpr.class, expr -> {
                    if (expr.getTarget() instanceof NameExpr) { // field = xxx;
                        String targetName = ((NameExpr)expr.getTarget()).getNameAsString();
                        if (fields.containsKey(targetName)) {
                            Variable v = fields.get(targetName);
                            out.add(v);
                            if(Args.ONLY_SAFE_TYPES_IN_TREE && !isTypeSafeForComparison(v.type))
                                tree_skip.set(true);
                        } else {
                            // maybe patch contains syntax error
                            System.out.printf("unknown variable name: %s\n", targetName);
                        }
                    } else if(
                        expr.getTarget() instanceof FieldAccessExpr &&
                        ((FieldAccessExpr)expr.getTarget()).getScope() instanceof ThisExpr
                    ) { // this.field = xxx;
                        String targetName = ((FieldAccessExpr)expr.getTarget()).getNameAsString();
                        if (fields.containsKey(targetName)) {
                            Variable v = fields.get(targetName);
                            out.add(v);
                            if(Args.ONLY_SAFE_TYPES_IN_TREE && !isTypeSafeForComparison(v.type))
                                tree_skip.set(true);
                        } else {
                            // maybe patch contains syntax error
                            System.out.printf("unknown variable name: %s\n", targetName);
                        }
                    } else if(mayContainDeepTarget(expr.getTarget(), fields)) { // e.g. field[i] = xxx;
                        tree_skip.set(true);
                    }
                    // assigned to fields/method calls/reflections...
                });

                // detect uncomparable retval
                if(!tree_skip.get() && !rettype_safe) {
                    stmt.walk(ReturnStmt.class, (ret)->{
                        Expression expr = ret.getExpression().orElse(null);
                        // everything other than `return;` and `return null;` are unsafe
                        if(expr!=null && !(expr instanceof NullLiteralExpr))
                            tree_skip.set(true);
                    });
                }

                // check deep sidefx method calls
                if(!tree_skip.get()) {
                    //long ts1 = System.nanoTime();

                    try {
                        stmt.walk(MethodCallExpr.class, (call)->{
                            if(tree_skip.get())
                                return; // skip if already rejected


                            if(!purity_source.isMethodCallPure(call)) {
                                tree_skip.set(true);
                            }
                        });
                    } catch (ParseProblemException e) {
                        System.out.println("sidefx analyzer parsing error!");
                    }

                    //long ts2 = System.nanoTime();

                    //if(!Args.POPULATE_CACHE_FOR_SYMBOL_SOLVER)
                    //    Main.total_offline_time_ns += ts2-ts1;
                }
            }

            shallow_sidefxs.add(out);
            should_tree_skip.add(tree_skip.get());
        }
    }

    private static final Set<String> SAFE_TYPES = new HashSet<>(Arrays.asList(
        "void",
        "int", "long", "float", "double", "boolean", "char", "byte", "short",
        "Integer", "Long", "Float", "Double", "Boolean", "Character", "Byte", "Short",
        "String", "StringBuilder", "StringBuffer", "BigDecimal", "Matcher", "Pattern"
    ));
    private static final Set<String> STD_WRAPPER_UNARY = new HashSet<>(Arrays.asList(
        "Set", "List", "ArrayList", "LinkedList", "HashSet", "TreeSet"
    ));
    private static final Set<String> STD_WRAPPER_BINARY = new HashSet<>(Arrays.asList(
        "Map", "HashMap", "TreeMap", "Hashtable", "WeakHashMap", "WeakHashtable"
    ));
    private boolean isTypeSafeForComparison(String t) {
        // arrays in java are compared conservatively, so it's okay to handle them in tree
        // https://stackoverflow.com/questions/16839182/can-an-array-be-used-as-a-hashmap-key
        if(t.endsWith("[]"))
            return true;

        if(SAFE_TYPES.contains(t))
            return true;

        if(t.endsWith(">")) {
            int spl = t.indexOf("<");
            String container_name = t.substring(0, spl);
            String inner_names = t.substring(spl+1, t.length()-1);

            if(STD_WRAPPER_UNARY.contains(container_name)) {
                return isTypeSafeForComparison(inner_names);
            } else if(STD_WRAPPER_BINARY.contains(container_name)) {
                int spl2 = inner_names.indexOf(",");
                if(spl2==-1)
                    return false;

                String left = inner_names.substring(0, spl2);
                String right = inner_names.substring(spl2+1, inner_names.length());
                if(right.contains(",")) // e.g. `Map<Map<a, b>, c>`, need serious parsing to handle this type, so just skip
                    return false;

                return isTypeSafeForComparison(left) && isTypeSafeForComparison(right);
            } else {
                return false;
            }
        }

        return false;
    }

    public Set<Variable> getShallowEffects(List<Statement> patch) {
        int idx = patch_to_idx.get(patch);
        return shallow_sidefxs.get(idx);
    }

    public boolean isHandleable(List<Statement> patch) {
        int idx = patch_to_idx.get(patch);
        return !should_tree_skip.get(idx);
    }
}
