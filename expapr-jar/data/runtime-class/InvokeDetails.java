package expressapr.testkit;

import java.util.HashMap;
import java.util.Objects;

public class InvokeDetails {
    private HashMap<String, Object> fields_before;
    private HashMap<String, Object> fields_changed;
    private TestKitExecResult res;

    @Override
    public boolean equals(Object o) {
        if (this == o) return true;
        if (o == null || getClass() != o.getClass()) return false;
        InvokeDetails that = (InvokeDetails) o;
        return fields_changed.equals(that.fields_changed) && res.equals(that.res);
    }

    @Override
    public int hashCode() {
        return Objects.hash(fields_changed, res);
    }

    public InvokeDetails() {
        fields_before = new HashMap<String, Object>();
        fields_changed = new HashMap<String, Object>();
        res = new TestKitExecResult();
    }

    public HashMap<String, Object> get_fields_changed() {
        return fields_changed;
    }
    public TestKitExecResult get_res() {
        return res;
    }

    void report_field_before(String name, Object value) {
        fields_before.put(name, value);
    }

    private boolean is_primitive_type(Class c) {
        return (
            c.equals(Boolean.class) || c.equals(Byte.class) || c.equals(Character.class) ||
            c.equals(Short.class) || c.equals(Integer.class) || c.equals(Long.class) ||
            c.equals(Float.class) || c.equals(Double.class)
        );
    }

    Object report_field_after_Object(String name, Object value) {
        if(!fields_before.containsKey(name)) { // generated vars
            fields_changed.put(name, value);

            // return null to "restore" to the original (unset) value
            return null;
        }
        Object orig = fields_before.get(name);
        if(!Objects.equals(orig, value))
            fields_changed.put(name, value);
        return orig;
    }
    // for primitive types, return default value to avoid NPE when unboxing
    Object report_field_after_byte(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Byte.valueOf((byte)0) : ret;
    }
    Object report_field_after_short(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Short.valueOf((short)0) : ret;
    }
    Object report_field_after_int(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Integer.valueOf((int)0) : ret;
    }
    Object report_field_after_long(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Long.valueOf((long)0) : ret;
    }
    Object report_field_after_float(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Float.valueOf((float)0) : ret;
    }
    Object report_field_after_double(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Double.valueOf((double)0) : ret;
    }
    Object report_field_after_boolean(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Boolean.valueOf(false) : ret;
    }
    Object report_field_after_char(String name, Object value) {
        Object ret = report_field_after_Object(name, value);
        return ret==null ? Character.valueOf('\0') : ret;
    }

    void report_exec_result(TestKitExecResult res) {
        this.res = res;
    }
}
