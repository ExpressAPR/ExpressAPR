package expressapr.testkit.internal_exceptions;

public class PatchContinue extends RuntimeException {
    public static void do_throw() {
        throw new PatchContinue();
    }
}
