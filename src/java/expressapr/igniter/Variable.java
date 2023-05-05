package expressapr.igniter;

import java.util.Objects;

public class Variable {
    public String type;
    public String name;
    public boolean is_final;

    static public final String NAME_PREFIX = "_testkitlocal_";

    @Override
    public String toString() {
        return "Variable{" +
            "type='" + type + '\'' +
            ", name='" + name + '\'' +
            ", is_final=" + is_final +
            '}';
    }

    public Variable(String type, String name, boolean is_final) {
        this.type = type;
        assert name!=null;
        this.name = name;
        this.is_final = is_final;
    }

    public static Variable pseudoVarForSearch(String name) {
        return new Variable(null, name, false);
    }

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        Variable variable = (Variable) o;
        return name.equals(variable.name);
    }

    @Override
    public int hashCode() {
        return Objects.hash(name);
    }

    /**
     * Old java (e.g. 1.5) refuses to convert an object directly to primitive, need some trick here.
     * e.g.
     *   double x = (double)obj; // -> compilation error
     *   double x = (Double)obj; // -> good, will be unboxed
     */
    public String objectVarType() {
        switch(type) {
            case "byte": return "java.lang.Byte";
            case "short": return "java.lang.Short";
            case "int": return "java.lang.Integer";
            case "long": return "java.lang.Long";
            case "float": return "java.lang.Float";
            case "double": return "java.lang.Double";
            case "boolean": return "java.lang.Boolean";
            case "char": return "java.lang.Character";
            default: return type; // not a primitive
        }
    }

    /**
     * To tackle with generics, object types are stored as Object.
     */
    public String objectKind() {
        switch(type) {
            case "byte":
            case "short":
            case "int":
            case "long":
            case "float":
            case "double":
            case "boolean":
            case "char":
                return type;
            default:
                return "Object";
        }
    }

    public String get_declare_statement(boolean is_static, boolean use_kind) {
        assert type!=null : "pseudo var for search cannot be declared";
        return "private " + (is_static ? "static " : "") + (use_kind ? objectKind() : type) + " " + NAME_PREFIX + name + ";";
    }
}
