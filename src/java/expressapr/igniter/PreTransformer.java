package expressapr.igniter;

import com.github.javaparser.*;
import com.github.javaparser.ast.CompilationUnit;
import com.github.javaparser.ast.Modifier;
import com.github.javaparser.ast.Node;
import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.body.*;
import com.github.javaparser.ast.expr.*;
import com.github.javaparser.ast.stmt.*;
import com.github.javaparser.ast.type.ClassOrInterfaceType;
import com.github.javaparser.ast.type.PrimitiveType;
import org.json.JSONArray;
import org.json.JSONObject;

import java.io.FileWriter;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.*;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

public class PreTransformer {
    final static StringTemplate TMPL_REFLECT_EXEC_RESULT = StringTemplate.fromTemplateName("ReflectExecResult");
    final static StringTemplate TMPL_RET_VALUE = StringTemplate.fromTemplateName("RetValue");
    final static StringTemplate TMPL_INST_FIELDS = StringTemplate.fromTemplateName("InstFields");
    final static StringTemplate TMPL_INST_METHODS = StringTemplate.fromTemplateName("InstMethods");
    final static StringTemplate TMPL_PATCH_WRAPPER = StringTemplate.fromTemplateName("PatchWrapper");
    final static StringTemplate TMPL_RUN_MODIFIED_CODE_CASE = StringTemplate.fromTemplateName("RunModifiedCodeCase");
    final static StringTemplate TMPL_APPLY_SAVED_CONTEXT_CASE = StringTemplate.fromTemplateName("ApplySavedContextCase");
    final static StringTemplate TMPL_REPORT_CONTEXT_BEFORE = StringTemplate.fromTemplateName("ReportContextBefore");
    final static StringTemplate TMPL_REPORT_RESTORE_CONTEXT_AFTER = StringTemplate.fromTemplateName("ReportRestoreContextAfter");
    final static StringTemplate TMPL_APPLY_SAVED_CONTEXT = StringTemplate.fromTemplateName("ApplySavedContext");
    final static StringTemplate TMPL_THROW_EXCEPTION_TO_PLEASE_COMPILER = StringTemplate.fromTemplateName("ThrowExceptionToPleaseCompiler");

    final static String MARK_CODEGEN_IP_POINT = "--TESTKIT--INSTRUMENT-POINT-HERE";
    final static String MARK_CODEGEN_IP_STUB = "--TESTKIT--CODEGEN-IP-STUB";
    final static String MARK_CODEGEN_CLASS_POINT = "--TESTKIT--CODEGEN-POINT-HERE";
    final public static String MARK_CODEGEN_PATCHSTART = "--TESTKIT--CODEGEN-PATCHSTART-";

    public List<Integer> orig_patchids; // map pid after removal -> orig pid

    // reported by verifier according to compiler errors

    private Set<String> vars_uninitialized_in_ip = new HashSet<>();
    private Set<String> final_vars_assigned_in_ip = new HashSet<>();
    private Set<Variable> final_fields_initialized_in_ip = new HashSet<>(); // it is possible in constructor
    private Set<String> caught_exception_in_ip = new HashSet<>();
    private boolean instrument_point_must_return = false;
    public boolean instrument_point_cannot_return = false;
    private boolean instrument_point_cannot_break = false;
    private boolean instrument_point_cannot_continue = false;

    private Set<String> report_in_this_turn = new HashSet<>();

    // initialized in constructor

    public String patches_json_fn;
    private String src_above;
    private String src_unpatched;
    private List<String> src_patches;
    private String src_below;

    private String src_allcode;
    CompilationUnit cu;

    private Range patch_range;
    private List<Integer> line_offsets;

    public JSONObject patch_config;

    private SideEffectAnalyzer sidefx_analyzer;

    // initialized in normalizePatchedAstInBlock

    private BlockStmt container_block;
    private CallableDeclaration<?> container_method; // maybe constructor
    public boolean container_method_is_constructor = false;
    private boolean container_method_is_generic = false;
    private ClassOrInterfaceDeclaration container_class;
    public String rettype;

    private boolean is_if_cond;
    private ExpressionStmt if_decl_stmt;

    private boolean schemata_use_static_fields;

    // initialized in collectPatchedStmts

    private List<Statement> stmts_unpatched;
    List<List<Statement>> stmts_patches;
    public boolean have_stmts_after_patch_area;

    /*-- ↑ PREPARE ----- CODEGEN ↓ --*/

    // initialized in collectVars

    private Map<String, Variable> vars_accessible_in_patch; // declared above the patch area, so that they are prefixed in occurrences
    private Map<String, Variable> vars_generated_in_patch; // declared in the unpatch code, and actually accessed by code below the patch area
    private List<Set<Variable>> fields_may_modified_in_patch; // including pseudo fields with prefixed name
    public List<Boolean> tree_handleable;

    // initialized in transformVarsInPatchedStmts

    private List<List<Statement>> transformed_stmts_patches;

    // initialized in generateInstrumentPoint

    private String codegen_ip;

    // initialized in generateClassFieldsAndMethods

    private String codegen_class;

    /**
     * Returns the position of the last char in str.
     */
    private static Position strEndpos(String str) {
        int line = 1 + (int)str.chars().filter((c)->c=='\n').count();
        int last_line_pos = str.lastIndexOf('\n') + 1;
        int col = str.length() - last_line_pos;
        return new Position(line, col);
    }

    /*
    static {
        // setup symbol solver
        TypeSolver type_solver = new CombinedTypeSolver();
        JavaSymbolSolver symbol_solver = new JavaSymbolSolver(type_solver);
        StaticJavaParser.getConfiguration().setSymbolResolver(symbol_solver);
    }
    */

    /**
     * "  foo bar " -> "   f"
     * "  " -> "  "
     * "xy" -> "x"
     */
    private static String substrTillFirstSignificantChar(String s) {
        int i = 0;
        for(; i<s.length(); i++) {
            char c = s.charAt(i);
            if(c!='\t' && c!=' ' && c!='\n') {
                i++;
                break;
            }
        }
        return s.substring(0, i);
    }
    /**
     * "  foo bar " -> "   foo bar"
     * "  " -> "  " (!)
     * "xy" -> "xy"
     */
    private static String substrTillLastSignificantChar(String s) {
        int idx = s.length()-1;
        for(int i=0; i<s.length(); i++) {
            char c = s.charAt(i);
            if(c!='\t' && c!=' ' && c!='\n')
                idx = i;
        }
        return s.substring(0, idx+1);
    }

    public PreTransformer(String patches_json_fn) throws IOException {
        this.patches_json_fn = patches_json_fn;
        readFromJSON(patches_json_fn);
        //readFromSrc("data/temp/play.java");

        orig_patchids = new ArrayList<>();
        for(int i=1; i<=getPatchCount(); i++)
            orig_patchids.add(i);

        if(src_unpatched.isEmpty())
            src_unpatched = " "; // javaparser Range cannot represent empty range

        src_allcode = src_above + src_unpatched + src_below;
//        FileWriter writer = new FileWriter("data/temp/out.java");
//        writer.write(src_allcode);
//        writer.close();
        cu = StaticJavaParser.parse(src_allcode);
        TreeStringify.setup(cu);

        patch_range = new Range(
            strEndpos(src_above+substrTillFirstSignificantChar(src_unpatched)),
            strEndpos(src_above+substrTillLastSignificantChar(src_unpatched))
        );
        calcLineOffsets();

        sidefx_analyzer = new SideEffectAnalyzer(this);
    }

    private void calcLineOffsets() {
        line_offsets = new ArrayList<>();
        line_offsets.add(0); // skip [0]
        line_offsets.add(0); // line_offsets[1] = 0
        int off = -1;
        while((off=src_allcode.indexOf('\n', off+1))!=-1) {
            line_offsets.add(off+1); // src[off] is '\n', src[off+1] is first char at next line
        }
    }

    /**
     * Convert {line, col} to source string index.
     */
    private int strIdxFromPosition(Position pos) {
        assert pos.line>0;
        assert pos.column>0;
        return line_offsets.get(pos.line)+pos.column-1;
    }

    private void readFromJSON(String json_fn) throws IOException {
        String json_string = new String(Files.readAllBytes(Paths.get(json_fn)), StandardCharsets.UTF_8);
        JSONObject obj = new JSONObject(json_string);
        if(!obj.has("manifest_version") || (obj.getInt("manifest_version")!=2 && obj.getInt("manifest_version")!=3))
            throw new RuntimeException("json manifest version mismatch: "+json_fn);

        src_above = obj.getString("context_above");
        src_unpatched = obj.getString("unpatched");
        src_below = obj.getString("context_below");


        JSONArray json_patches = obj.getJSONArray("patches");

        src_patches = new ArrayList<>(json_patches.length());
        for(int i=0; i<json_patches.length(); i++)
            src_patches.add(json_patches.get(i).toString());

        patch_config = obj;
    }

    private void readFromSrc(String src_fn) throws IOException {
        String src_str = new String(Files.readAllBytes(Paths.get(src_fn)), StandardCharsets.UTF_8);
        final String begin_pattern = "/* BEGIN UNPATCHED */";
        final String end_pattern = "/* END UNPATCHED */";
        int pos_begin = src_str.indexOf(begin_pattern);
        int pos_end = src_str.indexOf(end_pattern);
        assert pos_begin!=-1;
        assert pos_end!=-1;
        src_above = src_str.substring(0, pos_begin);
        src_unpatched = src_str.substring(pos_begin + begin_pattern.length(), pos_end);
        src_below = src_str.substring(pos_end + end_pattern.length());

        ArrayList<String> pat = new ArrayList<>();
        Matcher pattern = Pattern.compile("/\\*--PATCH (.*?) --\\*/").matcher(src_str);
        while(pattern.find())
            pat.add(pattern.group(1));

        src_patches = new ArrayList<>(pat.size());
        src_patches.addAll(pat);
    }

    /**
     * Update field `container_block`, `container_method`, `container_class`.
     * Find AST of stmt corresponding to patched area, and its container block.
     * Special treatment is done so that
     *   `patched_ast` is always a stmt (might be a single stmt or a block), and
     *   `container_block` is `patched_ast` itself or its parent, which is always a `BlockStmt` anyway.
     */
    private void normalizePatchedAstInBlock() {
        // step 1: locate containing ast node

        List<Statement> patched_ast_candidates = cu.findAll(Statement.class, (node)->{
            Optional<Range> range = node.getRange();
            return range.isPresent() && range.get().contains(patch_range);
        });
        if(patched_ast_candidates.isEmpty())
            throw new RuntimeException("patch not in a statement");

        Statement patched_ast = patched_ast_candidates.get(patched_ast_candidates.size()-1);
        assert patched_ast.getParentNode().isPresent();

        //System.out.printf("containing stmt: <<%s>>\n", TreeStringify.print(patched_ast));

        // step 2: make it in a block stmt

        // if patched stmt is a labeled for, contain the label for it
        if(patched_ast.getParentNode().get() instanceof LabeledStmt)
            patched_ast = (LabeledStmt)patched_ast.getParentNode().get();

        // patched stmt is already multiple stmts in a block
        if(patched_ast instanceof BlockStmt) {
            container_block = (BlockStmt)patched_ast;
        }
        else {
            // patched stmt is a single stmt, now find its container block
            Node parent = patched_ast.getParentNode().get();

            // consider hanged body in SwitchEntry, IfStmt, DoStmt, WhileStmt, ForStmt, ForEachStmt

            if(parent instanceof SwitchEntry) {
                System.out.println("processing switch");
                SwitchEntry par = (SwitchEntry)parent;
                BlockStmt blk = new BlockStmt(par.getStatements());
                par.setStatements(new NodeList<>(blk));
                blk.getStatements().setParentNode(blk);
            }
            else if(parent instanceof IfStmt) {
                System.out.println("processing if");
                IfStmt par = (IfStmt)parent;
                BlockStmt blk = new BlockStmt(new NodeList<>(patched_ast));
                if(par.getThenStmt()==patched_ast)
                    par.setThenStmt(blk);
                else if(par.getElseStmt().isPresent() && par.getElseStmt().get()==patched_ast)
                    par.setElseStmt(blk);
                else
                    throw new RuntimeException("unknown position in parent if");
                blk.getStatements().setParentNode(blk);
            }
            else if(parent instanceof DoStmt) {
                System.out.println("processing do");
                DoStmt par = (DoStmt)parent;
                BlockStmt blk = new BlockStmt(new NodeList<>(patched_ast));
                if(par.getBody()==patched_ast)
                    par.setBody(blk);
                else
                    throw new RuntimeException("unknown position in parent do");
                blk.getStatements().setParentNode(blk);
            }
            else if(parent instanceof WhileStmt) {
                System.out.println("processing while");
                WhileStmt par = (WhileStmt)parent;
                BlockStmt blk = new BlockStmt(new NodeList<>(patched_ast));
                if(par.getBody()==patched_ast)
                    par.setBody(blk);
                else
                    throw new RuntimeException("unknown position in parent while");
                blk.getStatements().setParentNode(blk);
            }
            else if(parent instanceof ForStmt) {
                System.out.println("processing for");
                ForStmt par = (ForStmt)parent;
                BlockStmt blk = new BlockStmt(new NodeList<>(patched_ast));
                if(par.getBody()==patched_ast)
                    par.setBody(blk);
                else
                    throw new RuntimeException("unknown position in parent for");
                blk.getStatements().setParentNode(blk);
            }
            else if(parent instanceof ForEachStmt) {
                System.out.println("processing foreach");
                ForEachStmt par = (ForEachStmt)parent;
                BlockStmt blk = new BlockStmt(new NodeList<>(patched_ast));
                if(par.getBody()==patched_ast)
                    par.setBody(blk);
                else
                    throw new RuntimeException("unknown position in parent foreach");
                blk.getStatements().setParentNode(blk);
            }

            parent = patched_ast.getParentNode().get();
            assert parent instanceof BlockStmt : parent.getClass().getTypeName();
            container_block = (BlockStmt)parent;
        }

        assert container_block==patched_ast || container_block==patched_ast.getParentNode().get();

        container_method = container_block.findAncestor(MethodDeclaration.class).orElse(null);
        if(container_method==null) { // try constructor
            container_method = container_block.findAncestor(ConstructorDeclaration.class).orElse(null);
            container_method_is_constructor = true;
        }
        if(container_method==null)
            throw new RuntimeException("patch area not in a method");

        container_method.setLineComment(MARK_CODEGEN_CLASS_POINT);

        container_class = container_method.findAncestor(ClassOrInterfaceDeclaration.class).orElse(null);
        if(container_class==null)
            throw new RuntimeException("patch area not in a class");

        //noinspection SimplifiableConditionalExpression
        schemata_use_static_fields = (
            container_class.isInnerClass() ? false : // inner classes cannot have static fields or methods
            container_method.isStatic() ? true : // if the container method is static, we have to keep everything static
            container_class.isGeneric() ? false : // avoid static if the class have generic parameters which cannot be accessed statically
            true // otherwise, keep everything static, which is faster
        );
        rettype = (container_method instanceof ConstructorDeclaration) ? "void" : ((MethodDeclaration)container_method).getTypeAsString();
        if(container_method.getTypeParameters().size()>0) {
            System.out.println("deal with generic");
            container_method_is_generic = true;
        }

        // step 3: special treatment for detect if cond

        is_if_cond = false;
        if(patched_ast instanceof IfStmt) {
            Optional<Range> cond_range = ((IfStmt)patched_ast).getCondition().getRange();
            if(cond_range.isPresent() && cond_range.get().contains(patch_range))
                is_if_cond = true;
        }

        if(is_if_cond) {
            System.out.println("treat if cond");
            IfStmt patched_if = (IfStmt)patched_ast;

            // get idx of patched if in container block

            int idx_if_in_container = -1;
            for(int i=0; i<container_block.getStatements().size(); i++)
                if(container_block.getStatements().get(i)==patched_ast) {
                    idx_if_in_container = i;
                    break;
                }
            assert idx_if_in_container!=-1 : "patched if ast not found in container";

            // update if cond

            Expression if_exp = patched_if.getCondition();
            patched_if.setCondition(new NameExpr("testkitgen_ifcond"));

            // insert ifcond decl stmt

            if_decl_stmt = new ExpressionStmt(new VariableDeclarationExpr(
                new VariableDeclarator(
                    new PrimitiveType(PrimitiveType.Primitive.BOOLEAN),
                    "testkitgen_ifcond",
                    if_exp
                )
            ));
            if_decl_stmt.setParentNode(container_block);
            container_block.addStatement(idx_if_in_container, if_decl_stmt);

            assert container_block==patched_ast.getParentNode().get();
        }
    }

    /**
     * Append into `sb_pfx` and `sb_sfx` so that
     * `sb_pfx + code in patch_range + sb_sfx == code in [begin, end]`
     */
    private void updateSfxPfxFromRange(StringBuilder sb_pfx, StringBuilder sb_sfx, Position begin, Position end) {
        assert begin.isBeforeOrEqual(patch_range.begin);
        sb_pfx.append(src_allcode, strIdxFromPosition(begin), strIdxFromPosition(patch_range.begin));

        if(!end.isAfterOrEqual(patch_range.end)) { // e.g. unpatched = `x=1; // any comment`
            assert src_unpatched.contains("//");
            return;
        }
        sb_sfx.append(src_allcode, strIdxFromPosition(patch_range.end)+1, strIdxFromPosition(end)+1);
    }

    private void addDeclIntoVarList(Map<String, Variable> li, VariableDeclarationExpr decl_stmt) {
        boolean is_final = decl_stmt.isFinal();

        for(VariableDeclarator decl: decl_stmt.getVariables()) {
            li.put(decl.getNameAsString(), new Variable(
                decl.getTypeAsString(), // type
                decl.getNameAsString(), // name
                is_final // is_final
            ));
        }
    }
    // xxx: this is literally same as the method above, but i failed to merge `FieldDeclaration` with `VariableDeclarationExpr`
    private void addDeclIntoVarList(Map<String, Variable> li, FieldDeclaration decl_stmt) {
        boolean is_final = decl_stmt.isFinal();

        for(VariableDeclarator decl: decl_stmt.getVariables()) {
            li.put(decl.getNameAsString(), new Variable(
                decl.getTypeAsString(), // type
                decl.getNameAsString(), // name
                is_final // is_final
            ));
        }
    }

    /**
     * Initialize field `stmts_unpatched` and `stmts_patches`.
     * Update field `container_block` to add marker for instrument point.
     * Expand patched area if necessary so that it consists of complete stmts.
     * Patch area is replaced with `INSTRUMENT_HERE_NAME`.
     */
    private void collectPatchedStmts() {
        // collect stmts_unpatched, also generate pfx and sfx to enlarge patch area into complete stmts

        stmts_unpatched = new ArrayList<>();
        StringBuilder sb_pfx = new StringBuilder();
        StringBuilder sb_sfx = new StringBuilder();

        if(is_if_cond) {
            Expression if_cond = (
                if_decl_stmt.getExpression().asVariableDeclarationExpr()
                    .getVariables().get(0)
                    .getInitializer().orElse(null)
            );
            assert if_cond!=null && if_cond.getRange().isPresent();
            Range if_cond_range = if_cond.getRange().get();
            sb_pfx.append("boolean testkitgen_ifcond = ");
            updateSfxPfxFromRange(sb_pfx, sb_sfx, if_cond_range.begin, if_cond_range.end);
            sb_sfx.append(";");

            stmts_unpatched.add(if_decl_stmt);
        } else { // normal stmts
            Position pos_begin = null;
            Position pos_end = null;
            for(Statement stmt: container_block.getStatements()) {
                assert stmt.getRange().isPresent();
                Range stmt_range = stmt.getRange().get();

                if(stmt_range.overlapsWith(patch_range)) {
                    if(pos_begin==null)
                        pos_begin = stmt_range.begin;
                    pos_end = stmt_range.end;

                    stmts_unpatched.add(stmt);
                }
            }
            if(pos_begin!=null && pos_end!=null) {
                updateSfxPfxFromRange(sb_pfx, sb_sfx, pos_begin, pos_end);
            } else {
                assert stmts_unpatched.isEmpty();
            }
        }

        // replace unpatched part to a MARK_INST_POINT

        int instrument_point_idx = -1;

        if(stmts_unpatched.isEmpty()) {
            for(int idx=0; idx<container_block.getStatements().size(); idx++) {
                Range stmt_range = container_block.getStatements().get(idx).getRange().orElse(null);
                if(stmt_range!=null && stmt_range.begin.isAfter(patch_range.end)) {
                    instrument_point_idx = idx;
                    break;
                }
            }
            if(instrument_point_idx==-1) // all stmts is before instrument point
                instrument_point_idx = container_block.getStatements().size();
        } else {
            for(int idx=0; idx<container_block.getStatements().size(); idx++) {
                if(container_block.getStatements().get(idx)==stmts_unpatched.get(0)) {
                    instrument_point_idx = idx;
                    break;
                }
            }
        }

        assert instrument_point_idx!=-1 : "failed to get instrument point";
        assert instrument_point_idx<=container_block.getStatements().size() : "instrument point out of range";

        for(Statement stmt: stmts_unpatched) {
            container_block.remove(stmt);
        }

        have_stmts_after_patch_area = container_block.getStatements().size()>instrument_point_idx;

        // xxx: JavaParser ignores comments for an empty stmt
        Statement ip_stmt = new EmptyStmt();
        container_block.getStatements().add(instrument_point_idx, ip_stmt);
        ip_stmt.setLineComment(MARK_CODEGEN_IP_POINT);

        // gen ast of patched_stmts

        stmts_patches = new ArrayList<>();

        for(String patch_str_raw: src_patches) {
            String patch_str = sb_pfx + patch_str_raw + sb_sfx;
            NodeList<Statement> parsed_stmts;
            try {
                BlockStmt blk = StaticJavaParser.parseBlock("{" + patch_str + "}");
                StaticJavaParser.parseBlock(blk.toString()); // xxx: parse `{();}` gets `{()->{};}`, which is invalid
                parsed_stmts = blk.getStatements();
            } catch(ParseProblemException e) {
                //e.printStackTrace();
                System.out.printf("failed to parse patch: << %s >>\n", patch_str);
                parsed_stmts = StaticJavaParser.parseBlock("{\"TESTKIT - patch parse failed\";}").getStatements();
            }
            stmts_patches.add(parsed_stmts);
        }
    }

    /**
     * Initialize field `vars_accessible_in_patch`, `fields_may_modified_in_patch` and `vars_generated_in_patch`.
     */
    private void collectVars() {
        assert container_block!=null;

        // collect fields

        Map<String, Variable> all_fields = new HashMap<>();
        for(BodyDeclaration<?> bodydecl: container_class.getMembers()) {
            if(bodydecl instanceof FieldDeclaration) {
                addDeclIntoVarList(
                    all_fields,
                    (FieldDeclaration)bodydecl
                );
            }
        }

        // find vars generated in patch area

        if(vars_generated_in_patch==null || final_fields_initialized_in_ip==null) {
            vars_generated_in_patch = new HashMap<>();
            final_fields_initialized_in_ip = new HashSet<>();

            for(Statement stmt: stmts_unpatched) {
                if( // only look for top-level decls
                    stmt instanceof ExpressionStmt &&
                        ((ExpressionStmt)stmt).getExpression() instanceof VariableDeclarationExpr
                ) {
                    addDeclIntoVarList(
                        vars_generated_in_patch,
                        (VariableDeclarationExpr)((ExpressionStmt)stmt).getExpression()
                    );
                }
            }

            // filter only accessed below patch area, so that patched code really needs to generate them

            // xxx: it is unsound if var names in inner scope shadow outer scopes (e.g. inner classes)
            HashSet<String> really_accessed_below_patch = new HashSet<>();
            for(Statement stmt: container_block.getStatements()) {
                if(
                    stmt.getRange().isPresent() &&
                        (is_if_cond ? // patch range for if_cond is in the if statement, which should be included
                            stmt.getRange().get().end.isAfter(patch_range.end) :
                            stmt.getRange().get().isAfter(patch_range.end)
                        )
                ) {
                    stmt.walk(NameExpr.class, (expr)->really_accessed_below_patch.add(expr.getNameAsString()));
                }
            }

            vars_generated_in_patch.keySet().removeIf((name)->!really_accessed_below_patch.contains(name));

            // final_fields_initialized_in_ip

            if(container_method_is_constructor)
                for(Statement stmt: stmts_unpatched) {
                    stmt.walk(AssignExpr.class, expr -> {
                        if (expr.getTarget() instanceof NameExpr) { // field = xxx;
                            String name = ((NameExpr)expr.getTarget()).getNameAsString();
                            if(all_fields.containsKey(name)) {
                                Variable var = all_fields.get(name);

                                if(var.is_final)
                                    final_fields_initialized_in_ip.add(var);
                            }
                        } else if(
                            expr.getTarget() instanceof FieldAccessExpr &&
                            ((FieldAccessExpr)expr.getTarget()).getScope() instanceof ThisExpr
                        ) { // this.field = xxx;
                            String name = ((FieldAccessExpr)expr.getTarget()).getNameAsString();
                            if(all_fields.containsKey(name)) {
                                Variable var = all_fields.get(name);

                                if(var.is_final)
                                    final_fields_initialized_in_ip.add(var);
                            }
                        }
                    });
                }
        }

        // find accessible vars in patch

        if(vars_accessible_in_patch==null) {
            vars_accessible_in_patch = new HashMap<>();

            // collect decls: walk up the container_block until method body
            for (
                Node node = container_block;
                node!=null && !(node instanceof MethodDeclaration);
                node = node.getParentNode().orElse(null)
            ) {
                if (node instanceof BlockStmt) {
                    for (Node sub: node.getChildNodes())
                        if(
                            sub instanceof ExpressionStmt &&
                                sub.getRange().isPresent() &&
                                sub.getRange().get().isBefore(patch_range.begin) &&
                                ((ExpressionStmt)sub).getExpression() instanceof VariableDeclarationExpr
                        ) {
                            addDeclIntoVarList(
                                vars_accessible_in_patch,
                                (VariableDeclarationExpr)((ExpressionStmt)sub).getExpression()
                            );
                        }
                } else if (node instanceof ForEachStmt) {
                    addDeclIntoVarList(
                        vars_accessible_in_patch,
                        ((ForEachStmt) node).getVariable()
                    );
                } else if (node instanceof ForStmt) {
                    for(Node sub: ((ForStmt) node).getInitialization())
                        if(
                            sub instanceof VariableDeclarationExpr &&
                                sub.getRange().isPresent() &&
                                sub.getRange().get().isBefore(patch_range.begin)
                        ) {
                            addDeclIntoVarList(
                                vars_accessible_in_patch,
                                (VariableDeclarationExpr)sub
                            );
                        }
                } else if (node instanceof ExpressionStmt) {
                    if(
                        node.getRange().isPresent() &&
                            node.getRange().get().isBefore(patch_range.begin) &&
                            ((ExpressionStmt) node).getExpression() instanceof VariableDeclarationExpr
                    ) {
                        addDeclIntoVarList(
                            vars_accessible_in_patch,
                            (VariableDeclarationExpr)((ExpressionStmt)node).getExpression()
                        );
                    }
                }
            }
            // args are also accessible vars
            for(Parameter param: container_method.getParameters()) {
                vars_accessible_in_patch.put(param.getNameAsString(), new Variable(
                    param.isVarArgs() ? (param.getTypeAsString()+"[]") : param.getTypeAsString(),
                    param.getNameAsString(),
                    param.isFinal()
                ));
                if(param.isFinal())
                    final_vars_assigned_in_ip.add(param.getNameAsString());
            }

            // generated final fields is a special kind of var
            for(Variable var: final_fields_initialized_in_ip) {
                vars_accessible_in_patch.put(var.name, var);
                vars_uninitialized_in_ip.add(var.name);
                final_vars_assigned_in_ip.add(var.name);
            }

            // merge pseudo fields from localvar
            for(Variable var: vars_accessible_in_patch.values())
                all_fields.put(var.name, new Variable(
                    var.type,
                    Variable.NAME_PREFIX + var.name,
                    var.is_final)
                );

            // collect fields and vars accessed in patch

            HashSet<String> varnames_really_accessed_in_patch = new HashSet<>();

            List<List<Statement>> li = new ArrayList<>(stmts_patches);
            // also mark vars in unpatched stmts as accessed
            // this will add them to restored var list after ip
            // eliminating compile errors "uninitialized variable" when a patch doesn't write to a local var
            li.add(stmts_unpatched);

            for(List<Statement> patch: li) {
                for(Statement stmt: patch) {
                    stmt.walk(NameExpr.class, (expr)->{
                        String name = expr.getNameAsString();
                        if(!all_fields.containsKey(name)) {
                            return; // maybe some external name or just a faulty patch, leave it to javac
                        }

                        if(vars_accessible_in_patch.containsKey(name))
                            varnames_really_accessed_in_patch.add(name);
                    });
                }
            }

            // filter vars_accessible_in_patch to only vars really accessed in patch

            vars_accessible_in_patch.keySet().removeIf((name)->!varnames_really_accessed_in_patch.contains(name));
        }

        // side effect analysis

        if(fields_may_modified_in_patch==null || tree_handleable==null) {
            fields_may_modified_in_patch = new ArrayList<>();
            tree_handleable = new ArrayList<>();

            sidefx_analyzer.analyze(all_fields);

            for(List<Statement> patch: stmts_patches) {
                Set<Variable> fields_may_modified = sidefx_analyzer.getShallowEffects(patch);
                fields_may_modified_in_patch.add(fields_may_modified);
                tree_handleable.add(sidefx_analyzer.isHandleable(patch));
            }
        }
    }

    /**
     * Initialize field `transformed_stmts_patches`.
     * Transform `NameExpr`s in patched stmts so that they point to prefixed name.
     */
    private void transformVarsInPatchedStmts() {

        transformed_stmts_patches = new ArrayList<>();

        // modify each patch, so that ...

        for(List<Statement> orig_patch : stmts_patches) {
            // clone them before we tamper

            List<Statement> tr_patch = orig_patch.stream()
                .map(Statement::clone)
                .collect(Collectors.toList());
            transformed_stmts_patches.add(tr_patch);

            // for names accessed: rename them

            for(Statement stmt: tr_patch) {
                stmt.walk(NameExpr.class, (expr)->{
                    String name = expr.getNameAsString();
                    if(vars_accessible_in_patch.containsKey(name))
                        expr.setName(Variable.NAME_PREFIX + name);
                });
            }

            // also consider final fields

            for(Statement stmt: tr_patch) {
                stmt.walk(FieldAccessExpr.class, (expr)->{
                    if(expr.getScope() instanceof ThisExpr) {
                        String name = expr.getNameAsString();
                        if(final_fields_initialized_in_ip.contains(Variable.pseudoVarForSearch(name)))
                            expr.setName(Variable.NAME_PREFIX + name);
                    }
                });
            }

            // for names generated: export at the end

            for(Variable var: vars_generated_in_patch.values()) {
                tr_patch.add(new ExpressionStmt(new AssignExpr(
                    new NameExpr(Variable.NAME_PREFIX + var.name),
                    new NameExpr(var.name),
                    AssignExpr.Operator.ASSIGN
                )));
            }
        }
    }

    /**
     * Set flag `instrument_point_cannot_*` in advance if this is the case.
     * This process saves time and avoids compile errors (e.g. `break`ing in ip may cause missing-return error).
     */
    private void detectCtrlFlowInPatches() {
        if(is_if_cond) {
            // expr in if cond cannot break or continue
            instrument_point_cannot_break = true;
            instrument_point_cannot_continue = true;
            instrument_point_cannot_return = true;
        } else {
            // check if patches do not actually break or continue
            AtomicBoolean found_break = new AtomicBoolean(false);
            AtomicBoolean found_continue = new AtomicBoolean(false);
            AtomicBoolean found_return = new AtomicBoolean(false);
            for(List<Statement> patch: stmts_patches) {
                for(Statement stmt: patch) {
                    stmt.walk(BreakStmt.class, (_s)-> found_break.set(true));
                    stmt.walk(ContinueStmt.class, (_s)-> found_continue.set(true));
                    stmt.walk(ReturnStmt.class, (_s)-> found_return.set(true));
                }
            }
            if(!found_break.get())
                instrument_point_cannot_break = true;
            if(!found_continue.get())
                instrument_point_cannot_continue = true;
            if(!found_return.get())
                instrument_point_cannot_return = true;
        }
    }

    /**
     * Initialize `codegen_ip`.
     * Add instrument routine at patch area.
     */
    private void generateInstrumentPoint() {
        ArrayList<Statement> instrument_stmts = new ArrayList<>();

        // save local vars

        for(Variable var: vars_accessible_in_patch.values())
            if(!vars_uninitialized_in_ip.contains(var.name))
                instrument_stmts.add(new ExpressionStmt(new AssignExpr(
                    new NameExpr(Variable.NAME_PREFIX + var.name),
                    new NameExpr(var.name),
                    AssignExpr.Operator.ASSIGN
                )));

        // call stub

        ExpressionStmt call_stub_stmt = new ExpressionStmt(new MethodCallExpr("_testkit_stub"));
        call_stub_stmt.setLineComment(MARK_CODEGEN_IP_STUB);
        instrument_stmts.add(call_stub_stmt);

        // restore local vars

        for(Variable var: final_fields_initialized_in_ip) {
            instrument_stmts.add(new ExpressionStmt(new AssignExpr(
                new FieldAccessExpr(new ThisExpr(), var.name),
                container_method_is_generic ?
                    new CastExpr(StaticJavaParser.parseType(var.type), new NameExpr(Variable.NAME_PREFIX + var.name)) :
                    new NameExpr(Variable.NAME_PREFIX + var.name),
                AssignExpr.Operator.ASSIGN
            )));
        }

        for(Variable var: vars_accessible_in_patch.values())
            if(!final_vars_assigned_in_ip.contains(var.name)) // skip already assigned final vars
                instrument_stmts.add(new ExpressionStmt(new AssignExpr(
                    new NameExpr(var.name),
                    container_method_is_generic ?
                        new CastExpr(StaticJavaParser.parseType(var.type), new NameExpr(Variable.NAME_PREFIX + var.name)) :
                        new NameExpr(Variable.NAME_PREFIX + var.name),
                    AssignExpr.Operator.ASSIGN
                )));
        for(Variable var: vars_generated_in_patch.values())
            instrument_stmts.add(new ExpressionStmt(new VariableDeclarationExpr(
                var.is_final ? new NodeList<>(Modifier.finalModifier()) : new NodeList<>(),
                new NodeList<>(new VariableDeclarator(
                    StaticJavaParser.parseType(var.type),
                    var.name,
                    container_method_is_generic ?
                        new CastExpr(StaticJavaParser.parseType(var.type), new NameExpr(Variable.NAME_PREFIX + var.name)) :
                        new NameExpr(Variable.NAME_PREFIX + var.name)
                ))
            )));

        // reflect exec result

        instrument_stmts.addAll(StaticJavaParser.parseBlock(
            TMPL_REFLECT_EXEC_RESULT
                .set(
                    "RET_VALUE",
                    "void".equals(rettype) ?
                        "" :
                        TMPL_RET_VALUE.set("RET_TYPE", new Variable(rettype, "_ret", false).objectVarType()).done()
                )
                .set("COMMENTOUT_IF_CANNOT_BREAK", instrument_point_cannot_break ? "//" : "")
                .set("COMMENTOUT_UNLESS_CANNOT_BREAK", instrument_point_cannot_break ? "" : "//")
                .set("COMMENTOUT_IF_CANNOT_CONTINUE", instrument_point_cannot_continue ? "//" : "")
                .set("COMMENTOUT_UNLESS_CANNOT_CONTINUE", instrument_point_cannot_continue ? "" : "//")
                .set("COMMENTOUT_IF_CANNOT_RETURN", instrument_point_cannot_return ? "//" : "")
                .set("COMMENTOUT_UNLESS_CANNOT_RETURN", instrument_point_cannot_return ? "" : "//")
                .done()
        ).getStatements());

        // control flow goes on

        if(instrument_point_must_return) {
            // patch fails to return
            instrument_stmts.add(new ThrowStmt(new ObjectCreationExpr(
                null,
                new ClassOrInterfaceType(null, "Error"),
                new NodeList<>(new StringLiteralExpr("PATCH DOES NOT RETURN AS REQUIRED"))
            )));
        }

        // throw checked exceptions to make compiler happy

        for(String exp: caught_exception_in_ip)
            instrument_stmts.addAll(StaticJavaParser.parseBlock(
                TMPL_THROW_EXCEPTION_TO_PLEASE_COMPILER.set(
                    "EXP_NAME",
                    exp
                ).done()
            ).getStatements());

        // store into codegen_ip

        StringBuilder ip_sb = new StringBuilder();
        for(Statement stmt: instrument_stmts) {
            ip_sb.append(stmt.toString());
            ip_sb.append("\n");
        }

        codegen_ip = "\n/*-- BEGIN TESTKIT CODEGEN IP --*/\n" + ip_sb + "\n/*-- END TESTKIT CODEGEN IP --*/\n";
    }

    /**
     * Initialize  `codegen_class`.
     * Add necessary fields and methods for instrumentation.
     * Each patch is wrapped into a method.
     */
    private void generateClassFieldsAndMethods() {
        StringBuilder sb = new StringBuilder();

        // local decls in fields

        for(Variable var: vars_accessible_in_patch.values()) {
            sb.append(var.get_declare_statement(schemata_use_static_fields, container_method_is_generic));
            sb.append("\n");
        }
        for(Variable var: vars_generated_in_patch.values()) {
            sb.append(var.get_declare_statement(schemata_use_static_fields, container_method_is_generic));
            sb.append("\n");
        }

        // common fields

        boolean is_static = container_method.isStatic();
        String rettype = (container_method instanceof ConstructorDeclaration) ? "void" : ((MethodDeclaration)container_method).getTypeAsString();
        int patches = transformed_stmts_patches.size();

        sb.append(
            TMPL_INST_FIELDS
                .set("MAYBE_STATIC", schemata_use_static_fields ? "static" : "")
                .doneWithNewline()
        );

        // common methods

        StringBuilder run_code_sb = new StringBuilder();
        for(int idx=0; idx<patches; idx++)
            run_code_sb.append(
                TMPL_RUN_MODIFIED_CODE_CASE
                    .set("PATCH_ID", String.valueOf(idx+1))
                    .doneWithNewline()
            );

        StringBuilder apply_ctx_sb = new StringBuilder();
        for(int idx=0; idx<patches; idx++)
            apply_ctx_sb.append(
                TMPL_APPLY_SAVED_CONTEXT_CASE
                    .set("PATCH_ID", String.valueOf(idx+1))
                    .doneWithNewline()
            );

        sb.append(
            TMPL_INST_METHODS
                .set("MAYBE_STATIC", is_static ? "static" : "")
                .set("RUN_MODIFIED_CODE_CASES", run_code_sb.toString())
                .set("APPLY_SAVED_CONTEXT_CASES", apply_ctx_sb.toString())
                .doneWithNewline()
        );

        // each patch wrapper

        for(int idx=0; idx<patches; idx++) {
            StringBuilder patch_body_sb = new StringBuilder();
            for(Statement stmt: transformed_stmts_patches.get(idx)) {
                patch_body_sb.append(stmt.toString());
                patch_body_sb.append("\n");
            }

            StringBuilder before_sb = new StringBuilder();

            for(Variable var: fields_may_modified_in_patch.get(idx))
                before_sb.append(
                    TMPL_REPORT_CONTEXT_BEFORE
                        .set("VARNAME", var.name)
                        .doneWithNewline()
                );

            StringBuilder after_sb = new StringBuilder();

            for(Variable var: fields_may_modified_in_patch.get(idx))
                after_sb.append(
                    TMPL_REPORT_RESTORE_CONTEXT_AFTER
                        .set("KIND", var.objectKind())
                        .set("VARTYPE", container_method_is_generic ? var.objectKind() : var.objectVarType())
                        .set("VARNAME", var.name)
                        .doneWithNewline()
                );
            for(Variable var: vars_generated_in_patch.values())
                after_sb.append(
                    TMPL_REPORT_RESTORE_CONTEXT_AFTER
                        .set("KIND", var.objectKind())
                        .set("VARTYPE", container_method_is_generic ? var.objectKind() : var.objectVarType())
                        .set("VARNAME", Variable.NAME_PREFIX + var.name)
                        .doneWithNewline()
                );

            StringBuilder apply_sb = new StringBuilder();

            for(Variable var: fields_may_modified_in_patch.get(idx))
                apply_sb.append(
                    TMPL_APPLY_SAVED_CONTEXT
                        .set("VARTYPE", container_method_is_generic ? var.objectKind() : var.objectVarType())
                        .set("VARNAME", var.name)
                        .doneWithNewline()
                );
            for(Variable var: vars_generated_in_patch.values())
                apply_sb.append(
                    TMPL_APPLY_SAVED_CONTEXT
                        .set("VARTYPE", container_method_is_generic ? var.objectKind() : var.objectVarType())
                        .set("VARNAME", Variable.NAME_PREFIX + var.name)
                        .doneWithNewline()
                );

            sb.append("//").append(MARK_CODEGEN_PATCHSTART).append(idx+1).append("\n");
            sb.append(
                TMPL_PATCH_WRAPPER
                    .set("MAYBE_STATIC", is_static ? "static" : "")
                    .set("RET_TYPE", container_method_is_generic ? new Variable(rettype, "_ret", false).objectKind() : rettype)
                    .set("PATCH_ID", String.valueOf(idx+1))
                    .set("PATCH_BODY", patch_body_sb.toString())
                    .set("REPORT_CONTEXT_BEFORE", before_sb.toString())
                    .set("REPORT_AND_RESTORE_CONTEXT_AFTER", after_sb.toString())
                    .set("COMMENTOUT_IF_NO_SAVED_CONTEXT", apply_sb.toString().isEmpty() ? "//" : "")
                    .set("APPLY_SAVED_CONTEXT", apply_sb.toString())
                    .set("COMMENTOUT_IF_VOID", "void".equals(rettype) ? "//" : "")
                    .set("COMMENTOUT_UNLESS_VOID", "void".equals(rettype) ? "" : "//")
                    .doneWithNewline()
            );
        }

        sb.append("//").append(MARK_CODEGEN_PATCHSTART).append(patches+1).append("\n");
        codegen_class = "\n/*-- BEGIN TESTKIT CODEGEN CLASS --*/\n" + sb + "\n/*-- END TESTKIT CODEGEN CLASS --*/\n";
    }

    /**
     * replace `// {before}` or `//{before}` to `{after}`.
     * This is because java parser may or may not add trailing space to the comment.
     */
    public static String commentReplace(String src, String before, String after) {
        if(src.contains("// "+before))
            return src.replace("// "+before, after);
        else if(src.contains("//"+before))
            return src.replace("//"+before, after);
        else
            throw new RuntimeException("commentReplace not found: "+before);
    }

    /**
     * Given all generated fields, produce full patched code.
     */
    private String joinPatchedCode() {
        String src = TreeStringify.print(cu);

        // remove `;` after codegen ip
        src = src.replaceFirst(MARK_CODEGEN_IP_POINT+"\\n\\s*;", MARK_CODEGEN_IP_POINT+"\n");

        src = commentReplace(src, MARK_CODEGEN_IP_POINT, codegen_ip);
        src = commentReplace(src, MARK_CODEGEN_CLASS_POINT, codegen_class);

        return src;
    }

    /**
     * Patch-selection-independent steps for generating instrumented code.
     * Patches may reduce (upon compilation error) afterwards.
     */
    public void preparePatches() {
        normalizePatchedAstInBlock();
        //System.out.printf("out: <<%s>>\n", LexicalPreservingPrinter.print(self.cu));
        //System.out.printf("transformed src: <<%s>>\n", cu);

        collectPatchedStmts();
        //System.out.printf("container block: <<%s>>\n", container_block);
        //System.out.printf("container method: <<%s>>\n", container_method.getNameAsString());
        //System.out.printf("patched stmts: %s\n", stmts_patches);

        sidefx_analyzer.initialize();

        collectVars();
        //System.out.printf("vars accessed: %s\n", vars_accessed_in_patch);
        //System.out.printf("vars generated: %s\n", vars_generated_in_patch);

        transformVarsInPatchedStmts();
        //System.out.printf("transformed patched stmts: %s\n", stmts_patches);

        detectCtrlFlowInPatches();

        System.out.println("preprare patches done.");
    }

    /**
     * Patch-selection-dependent steps.
     * This method is called once patch selection is changed.
     */
    public String generatePatches() {
        // recalculate vars_accessed_in_patch because the set may shrink after patch set is shrunk
        // this will speedup codegen_ip area because less field/localvar conversions are done
        vars_accessible_in_patch = null;
        collectVars();
        //System.out.printf("vars accessed: %s\n", vars_accessed_in_patch);
        //System.out.printf("vars generated: %s\n", vars_generated_in_patch);

        generateInstrumentPoint();
        //System.out.printf("codegen ip: <<%s>>\n", codegen_ip);

        generateClassFieldsAndMethods();
        //System.out.printf("codegen class: <<%s>>\n", codegen_class);

        return joinPatchedCode();
    }

    public void removePatches(Set<Integer> ids_set) {
        List<Integer> ids_list = new ArrayList<>(ids_set);
        Collections.sort(ids_list);
        Collections.reverse(ids_list);

        // now ids are in desc order
        for(int id: ids_list) {
            assert id>=1; // id starts from 1
            int idx = id-1;

            src_patches.remove(idx);
            stmts_patches.remove(idx);
            orig_patchids.remove(idx);
            transformed_stmts_patches.remove(idx);
            fields_may_modified_in_patch.remove(idx);
            tree_handleable.remove(idx);
        }
    }

    private boolean isJavaIdentifier(String s) {
        if(s.isEmpty())
            return false;
        if(!Character.isJavaIdentifierStart(s.charAt(0)))
            return false;
        for(int i=1; i<s.length(); i++)
            if(!Character.isJavaIdentifierPart(s.charAt(i)))
                return false;
        return true;
    }

    public int getPatchCount() {
        return src_patches.size();
    }

    public void reportInstrumentPointMustReturn() {
        if(instrument_point_must_return) {
            if(report_in_this_turn.contains("mustret"))
                return;
            throw new RuntimeException("still missing return statement");
        }
        if(instrument_point_cannot_return)
            throw new RuntimeException("reportInstrumentPointMustReturn conflict");

        instrument_point_must_return = true;

        report_in_this_turn.add("mustret");
        System.out.print("set reportInstrumentPointMustReturn\n");
    }

    public void reportUninitializedVar(String name) {
        assert isJavaIdentifier(name) : "uninitialized var name invalid: "+name;

        if(vars_uninitialized_in_ip.contains(name)) {
            if(report_in_this_turn.contains("uninit:"+name))
                return;
            throw new RuntimeException("var already reported as uninitialized: "+name);
        }

        vars_uninitialized_in_ip.add(name);

        report_in_this_turn.add("uninit:"+name);
        System.out.printf("set reportUninitializedVar %s\n", name);
    }

    public void reportFinalVarAssigned(String name) {
        assert isJavaIdentifier(name) : "assigned final var name invalid: "+name;

        if(final_vars_assigned_in_ip.contains(name)) {
            if(report_in_this_turn.contains("asgnfinal:"+name))
                return;
            throw new RuntimeException("var already reported as assigned final: "+name);
        }

        final_vars_assigned_in_ip.add(name);

        report_in_this_turn.add("asgnfinal:"+name);
        System.out.printf("set reportFinalVarAssigned %s\n", name);
    }

    public void reportCaughtExceptionName(String name) {
        assert isJavaIdentifier(name) : "caught exception name invalid: "+name;

        if(caught_exception_in_ip.contains(name)) {
            if(report_in_this_turn.contains("caughtexc:"+name))
                return;
            throw new RuntimeException("exception already reported as caught: "+name);
        }

        caught_exception_in_ip.add(name);

        report_in_this_turn.add("caughtexc:"+name);
        System.out.printf("set reportCaughtExceptionName %s\n", name);
    }

    public void reportInstrumentPointCannotBreak() {
        if(instrument_point_cannot_break) {
            if(report_in_this_turn.contains("cantbreak"))
                return;
            throw new RuntimeException("already reported cannot break");
        }

        instrument_point_cannot_break = true;

        report_in_this_turn.add("cantbreak");
        System.out.println("set reportInstrumentPointCannotBreak");
    }

    public void reportInstrumentPointCannotContinue() {
        if(instrument_point_cannot_continue) {
            if(report_in_this_turn.contains("cantcontn"))
                return;
            throw new RuntimeException("already reported cannot continue");
        }

        instrument_point_cannot_continue = true;

        report_in_this_turn.add("cantcontn");
        System.out.println("set reportInstrumentPointCannotContinue");
    }

    public void reportInstrumentPointCannotReturn() {
        if(instrument_point_must_return)
            throw new RuntimeException("reportInstrumentPointCannotReturn conflict");
        if(instrument_point_cannot_return) {
            if(report_in_this_turn.contains("cantret"))
                return;
            throw new RuntimeException("still requiring not to return");
        }

        instrument_point_cannot_return = true;

        report_in_this_turn.add("cantret");
        System.out.print("set reportInstrumentPointCannotReturn\n");
    }

    public void reportDone() {
        report_in_this_turn.clear();
    }

    public void precheckPatches() {
        // `{xxx; return; yyy;}` will cause compile error (unreachable statement) at `yyy;`
        if(have_stmts_after_patch_area) {
            Set<Integer> problematic_patches = new HashSet<>();
            for(int i=0; i<stmts_patches.size(); i++) {
                List<Statement> patch = stmts_patches.get(i);
                if(patch.size()==1) {
                    Statement stmt = patch.get(0);
                    if(
                        stmt instanceof ReturnStmt ||
                        stmt instanceof ThrowStmt ||
                        stmt instanceof BreakStmt ||
                        stmt instanceof ContinueStmt
                    ) {
                        System.out.printf("precheck filtered out patch #%d\n", i+1);
                        problematic_patches.add(i+1);
                    }
                }
            }

            removePatches(problematic_patches);
        }
    }

    public static void main(String[] args) throws IOException {
        SideEffectAnalyzer.purity_source = null;

        //Statement stmt = StaticJavaParser.parseStatement("Foo x;");
        String input_file = "data/temp/fail.json";
        String output_file = input_file.replace(".json", ".java");
        PreTransformer self = new PreTransformer(input_file);
        System.out.printf("full src: <<%s>>\n", TreeStringify.print(self.cu));

        self.preparePatches();
        self.precheckPatches();

        String out = self.generatePatches();
        System.out.printf("final src: <<%s>>", out);

        //self.removePatches(new HashSet<>(Arrays.asList(1, 2, 3)));
        //System.out.println("--- removed patches");

        //out = self.generatePatches();
        //System.out.printf("final src: <<%s>>", out);

        FileWriter writer = new FileWriter(output_file);
        writer.write(out);
        writer.close();
    }
}
