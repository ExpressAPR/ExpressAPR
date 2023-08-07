private [[[MAYBE_STATIC]]] [[[RET_TYPE]]] _testkit_modified_code_[[[PATCH_ID]]]() {
    if(true) {
        for(;;expressapr.testkit.internal_exceptions.PatchContinue.do_throw()) {
            if(true) {
                [[[PATCH_BODY]]]
            }
            throw new expressapr.testkit.internal_exceptions.PatchFinish();
        }
    }
    throw new expressapr.testkit.internal_exceptions.PatchBreak();
}

private [[[MAYBE_STATIC]]] void _testkit_run_modified_code_[[[PATCH_ID]]](boolean is_tree_run) {
    if(is_tree_run) {
        [[[REPORT_CONTEXT_BEFORE]]]
    }

    [[[--]]] long begin_ts = java.lang.System.nanoTime();
    try {
        [[[COMMENTOUT_IF_VOID]]] Object ret = _testkit_modified_code_[[[PATCH_ID]]]();
        [[[COMMENTOUT_UNLESS_VOID]]] _testkit_modified_code_[[[PATCH_ID]]](); Object ret = null;
        _testkit_exec_result.set_return(ret);
    } catch(expressapr.testkit.internal_exceptions.PatchFinish _t) {
        _testkit_exec_result.set_finish();
    } catch(expressapr.testkit.internal_exceptions.PatchBreak _t) {
        _testkit_exec_result.set_break();
    } catch(expressapr.testkit.internal_exceptions.PatchContinue _t) {
        _testkit_exec_result.set_continue();
    } catch(Throwable t) {
        _testkit_exec_result.set_throw_unchecked(t);
    }
    [[[--]]] long end_ts = java.lang.System.nanoTime();
    [[[--]]] _testkit_orchestrator.TELEMETRY_total_user_time_nano += (end_ts - begin_ts);

    if(is_tree_run) {
        [[[REPORT_AND_RESTORE_CONTEXT_AFTER]]]
    }
}

private [[[MAYBE_STATIC]]] void _testkit_apply_saved_context_[[[PATCH_ID]]](expressapr.testkit.InvokeDetails invoke) {
    _testkit_exec_result = invoke.get_res();
    [[[COMMENTOUT_IF_NO_SAVED_CONTEXT]]] java.util.HashMap<String, Object> fields_changed = invoke.get_fields_changed();
    [[[APPLY_SAVED_CONTEXT]]]
}