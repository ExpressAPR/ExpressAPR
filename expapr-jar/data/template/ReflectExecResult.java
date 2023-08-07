{
    if(_testkit_exec_result.is_throw_unchecked())
        _testkit_orchestrator.unsafe.throwException((Throwable)_testkit_exec_result.get_retval());
    else if(_testkit_exec_result.is_return())
        [[[COMMENTOUT_IF_CANNOT_RETURN]]] return [[[RET_VALUE]]];
        [[[COMMENTOUT_UNLESS_CANNOT_RETURN]]] org.junit.Assert.fail("TESTKIT: patch return causes compile error");
    else if(_testkit_exec_result.is_break())
        [[[COMMENTOUT_IF_CANNOT_BREAK]]] break;
        [[[COMMENTOUT_UNLESS_CANNOT_BREAK]]] org.junit.Assert.fail("TESTKIT: patch break causes compile error");
    else if(_testkit_exec_result.is_continue())
        [[[COMMENTOUT_IF_CANNOT_CONTINUE]]] continue;
        [[[COMMENTOUT_UNLESS_CANNOT_CONTINUE]]] org.junit.Assert.fail("TESTKIT: patch continue causes compile error");
}