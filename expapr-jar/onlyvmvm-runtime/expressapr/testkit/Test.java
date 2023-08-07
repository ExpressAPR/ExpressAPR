package expressapr.testkit;

public class Test {
    private Class<?> clazz;
    private String method;

    public double time_s;
    public boolean failed;

    Test(Class<?> clazz, String method) {
        this.clazz = clazz;
        this.method = method;
        this.time_s = 0;
        this.failed = false;
    }

    public Class<?> get_clazz() {
        return clazz;
    }
    public String get_method() {
        return method;
    }
}
