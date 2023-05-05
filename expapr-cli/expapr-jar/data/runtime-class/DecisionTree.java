package expressapr.testkit;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

public class DecisionTree {
    private TestResult result;
    private ArrayList<Integer> patches;
    private DecisionTree parent;
    private int subtree_expanding_count;

    // below: only valid for non-leaf nodes (i.e. result is InvokeExpanded)
    private HashMap<InvokeDetails, DecisionTree> child;

    DecisionTree(TestResult tr, DecisionTree par) {
        subtree_expanding_count = 0;
        parent = par;
        patches = new ArrayList<Integer>();
        child = new HashMap<InvokeDetails, DecisionTree>();
        set_result(tr);
    }

    public ArrayList<Integer> get_patches() {
        return patches;
    }
    public void add_into_patches(int pid) {
        patches.add(pid);
    }

    public int get_subtree_expanding_count() {
        return subtree_expanding_count;
    }

    public TestResult get_result() {
        return result;
    }
    public void set_result(TestResult tr) {
        if(result==TestResult.Expanding)
            modify_subtree_expanding_count(this, -1);
        result = tr;
        if(result==TestResult.Expanding)
            modify_subtree_expanding_count(this, 1);
    }

    private void modify_subtree_expanding_count(DecisionTree self, int delta) {
        while(self!=null) {
            self.subtree_expanding_count += delta;
            assert self.subtree_expanding_count>=0;
            self = self.parent;
        }
    }

    public DecisionTree get_child(InvokeDetails res) {
        assert result==TestResult.Expanding || result==TestResult.InvokeExpanded;
        return child.get(res);
    }
    public Set<Map.Entry<InvokeDetails, DecisionTree>> get_childs() {
        return child.entrySet();
    }

    private DecisionTree insert_child(InvokeDetails res, TestResult tr) {
        assert result==TestResult.Expanding;
        assert !child.containsKey(res);

        DecisionTree tree = new DecisionTree(tr, this);
        child.put(res, tree);
        return tree;
    }

    public DecisionTree get_or_insert_child(InvokeDetails res, TestResult tr, int patchid) {
        DecisionTree tree = get_child(res);
        if(tree==null)
            tree = insert_child(res, tr);

        tree.patches.add(patchid);
        return tree;
    }
}
