private [[[MAYBE_STATIC]]] void _testkit_stub() {
    [[[--]]] long begin_ts = java.lang.System.nanoTime();
    if(_testkit_orchestrator.is_tree_run()) {
        _testkit_orchestrator.tree_sancheck();

        expressapr.testkit.TestResult tr = _testkit_orchestrator.get_tree_result();
        //assert tr==expressapr.testkit.TestResult.Expanding || tr==expressapr.testkit.TestResult.InvokeExpanded; // enforced in sancheck

        if(tr==expressapr.testkit.TestResult.Expanding) {
            for(int patchid: _testkit_orchestrator.get_patches()) {
                _testkit_orchestrator.report_before_invoke();
                _testkit_run_modified_code(patchid, true);
                _testkit_orchestrator.report_after_invoke(_testkit_exec_result, patchid);
            }
            _testkit_orchestrator.finish_expanding();
        }

        _testkit_apply_saved_context(_testkit_orchestrator.move_to_expandable_edge());
    } else { // single run
        _testkit_orchestrator.mark_single_run_touched();
        _testkit_run_modified_code(_testkit_orchestrator.get_patch_id(), false);
    }
    [[[--]]] long end_ts = java.lang.System.nanoTime();
    [[[--]]] _testkit_orchestrator.TELEMETRY_total_schemata_time_nano += (end_ts - begin_ts);
}

private [[[MAYBE_STATIC]]] void _testkit_run_modified_code(int patchid, boolean is_tree_run) {
    switch(patchid) {
        [[[RUN_MODIFIED_CODE_CASES]]]
        default: _testkit_orchestrator.report_fatal("patch id out of bound (in run_modified_code): "+patchid); assert false; break;
    }
}

private [[[MAYBE_STATIC]]] void _testkit_apply_saved_context(java.util.Map.Entry<expressapr.testkit.InvokeDetails, expressapr.testkit.DecisionTree> edge) {
    int patchid = edge.getValue().get_patches().get(0);
    expressapr.testkit.InvokeDetails invoke = edge.getKey();
    switch(patchid) {
        [[[APPLY_SAVED_CONTEXT_CASES]]]
        default: _testkit_orchestrator.report_fatal("patch id out of bound (in apply_saved_context): "+patchid); break;
    }
}