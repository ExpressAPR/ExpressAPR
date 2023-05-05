package expressapr.testkit;

public class Test {
    private String clazzname;
    private String method;
    DecisionTree tree;

    Test(String clazzname, String method) {
        this.clazzname = clazzname;
        this.method = method;
        this.tree = new DecisionTree(TestResult.Expanding, null);
    }

    public String get_clazzname() {
        return clazzname;
    }
    public Class<?> get_clazz() {
        try {
            return Class.forName(clazzname);
        } catch (ClassNotFoundException e) {
            e.printStackTrace();
            return null;
        }
    }
    public String get_method() {
        return method;
    }
    public DecisionTree get_tree() {
        return tree;
    }

    public boolean equals(Object obj) {
        if (obj instanceof Test) {
            Test other = (Test) obj;
            return clazzname.equals(other.clazzname) && method.equals(other.method);
        }
        return false;
    }
    public int hashCode() {
        // not `Objects.hash` here because it is JDK 1.7+
        return clazzname.hashCode() + method.hashCode();
    }
}
