package expressapr.igniter.purity;

import com.github.javaparser.ast.expr.MethodCallExpr;

import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

public class TrivialPuritySource implements AbstractPuritySource {
    @Override
    public boolean isMethodCallPure(MethodCallExpr call) {
        String method_name = call.getNameAsString();
        return ALWAYS_PURE_METHODS.contains(method_name);
    }

    private static final Set<String> ALWAYS_PURE_METHODS = new HashSet<>(Arrays.asList(
        // pure std methods
        "hashCode", "equals", "toString", "getClass", "clone", "valueOf",

        // container methods
        "length", "size", "contains", "get", "isEmpty",

        // string methods
        "charAt", "substring", "indexOf", "lastIndexOf", "isWhitespace", "startsWith", "endsWith", "concat",

        // numeric methods
        "isNaN", "isInfinite", "gcd", "sqrt", "abs", "multiply", "scalb", "mulAndCheck", "getExponent", "ulp", "max",

        // common pure methods
        //"getType", "getCharno", "getLineno", "getNext", "getString", "getFirstChild", "getIndex",
        //"getQualifiedName", "getPeriod", "createComplex",

        "__fuck_java_arglist_not_allowed_to_have_trailing_comma"
    ));
}
