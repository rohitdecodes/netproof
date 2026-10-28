from netproof.intent import Flow, FlowResult, compare, is_healthy

A = Flow("a", "x", "y", "tcp", 80, "allow")
D = Flow("d", "x", "z", "icmp", None, "deny")


def res(a_reach, d_reach):
    return {"a": FlowResult(A, a_reach), "d": FlowResult(D, d_reach)}


def test_improvement_without_regression():
    c = compare(res(False, False), res(True, False))
    assert c.improvements == ["a"] and c.regressions == []


def test_opening_a_denied_flow_is_a_regression():
    c = compare(res(False, False), res(True, True))
    assert c.regressions == ["d"]


def test_healthy():
    assert is_healthy(res(True, False))
    assert not is_healthy(res(True, True))
