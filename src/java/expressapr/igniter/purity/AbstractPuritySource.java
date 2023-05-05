package expressapr.igniter.purity;

import com.github.javaparser.ast.NodeList;
import com.github.javaparser.ast.expr.MethodCallExpr;
import com.github.javaparser.ast.stmt.Statement;

public interface AbstractPuritySource {
    /**
     * Called once of each cluster.
     */
    default void initialize() {}

    /**
     * Also called once at the beginning of the analysis of each cluster.
     * But this time with the list of patches.
     */
    default void initializeForPatches(NodeList<Statement> patches) {}

    @SuppressWarnings("BooleanMethodIsAlwaysInverted")
    boolean isMethodCallPure(MethodCallExpr call);
}
