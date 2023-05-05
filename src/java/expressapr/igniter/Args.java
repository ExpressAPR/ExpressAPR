package expressapr.igniter;

public class Args {
    // Main
    public static boolean TEST_SEL_WHEN_NODEDUP = false;

    // PatchVerifier
    final public static long COMPILE_TIMEOUT_MS_EACH = 5000;
    final public static long COMPILE_TIMEOUT_MS_MAX = 180000;
    final public static long COMPILE_TIMEOUT_MS_BASE = 30000;
    public static boolean WRITE_COMPILER_MSG = false;

    // StringTemplate
    public static boolean RUNTIME_DEBUG = false;
    public static boolean WRITE_TEMPLATE_NAME = false;

    // TreeStringify
    final public static boolean USE_LEXICAL_PRINTING = false;

    // SideEffectAnalyzer
    final public static boolean ONLY_SAFE_TYPES_IN_TREE = true;

    // SidefxDbSource
    final public static boolean POPULATE_CACHE_FOR_SYMBOL_SOLVER = false;
}
