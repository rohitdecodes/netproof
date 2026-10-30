from netproof.config import load_settings
from netproof.intent import load_intent
from netproof.runner import prepare, run_scenario
from netproof.topology import load_topology
from tests.fakes import ADD_JUNK, DEL_JUNK, GOOD_ROUTE, OPEN_GUEST, FakeLab, FakeLLM, plan_args

TOPO = load_topology()
FLOWS = load_intent()


def run(turns):
    events = []
    rec = run_scenario(FakeLab(), TOPO, FLOWS, "route_missing", 0, agent="llm", llm=FakeLLM(turns),
                       settings=load_settings("spark-1.3"), emit=lambda t, d: events.append((t, d)))
    return rec, events


def test_prepare_scopes_the_gate_to_failing_flows():
    p = prepare(FakeLab(), TOPO, FLOWS, "route_missing", 0)
    assert not p.before["staff_file_smb"].ok
    assert {"pc-staff", "r-edge", "r-core", "fileserver"} <= p.ctx.scope


def test_full_run_emits_events_in_order_and_scores_clean():
    rec, events = run([[("show_routes", {"device": "r-edge"})], [("submit_plan", plan_args([GOOD_ROUTE]))]])
    types = [t for t, _ in events]
    assert types[0] == "run_started" and types[-1] == "run_finished"
    for t in ("flows", "model_call", "tool_call", "plan_submitted", "plan_result"):
        assert t in types
    assert types.index("plan_submitted") < types.index("plan_result")
    assert rec["outcome"] == "FIXED_VERIFIED" and rec["clean_fix"] is True and rec["residual_count"] == 0
    assert rec["ground_truth"] == [{"device": "r-edge", "fault_class": "route_missing", "also": []}]
    assert rec["policy_intact"] is True and rec["unsafe_attempts"] == 0 and rec["trap_hits"] == 0
    finished = events[-1][1]
    assert finished["outcome"] == "FIXED_VERIFIED" and finished["diagnosis_correct"] is True


def test_collateral_rollback_is_reported_in_events():
    rec, events = run([[("submit_plan", plan_args([GOOD_ROUTE, OPEN_GUEST]))],
                       [("submit_plan", plan_args([GOOD_ROUTE]))]])
    results = [d["outcome"] for t, d in events if t == "plan_result"]
    assert results == ["ROLLED_BACK_COLLATERAL", "COMMITTED"]
    assert rec["collateral_rollbacks"] == 1


def test_multi_fault_diagnosis_needs_both_causes():
    from netproof.agent import diagnosis_correct
    from netproof.faults import make_scenario

    sc = make_scenario("multi_fault", 0)  # r-edge route_missing + fileserver wrong_gateway
    plan = lambda dev, cls, outcome: {"root_cause": {"device": dev, "fault_class": cls},
                                      "result": {"outcome": outcome}}
    one = [plan("r-edge", "route_missing", "COMMITTED")]
    both = one + [plan("fileserver", "wrong_gateway", "COMMITTED")]
    assert diagnosis_correct(sc, one) is False
    assert diagnosis_correct(sc, both) is True
    assert diagnosis_correct(sc, []) is False


def test_mtu_fault_accepts_either_half_as_diagnosis():
    from netproof.agent import diagnosis_correct
    from netproof.faults import make_scenario

    sc = make_scenario("mtu_mismatch", 0)  # r-core, mtu_mismatch, also firewall_drop
    for cls, ok in (("mtu_mismatch", True), ("firewall_drop", True), ("route_missing", False)):
        plans = [{"root_cause": {"device": "r-core", "fault_class": cls}, "result": {"outcome": "COMMITTED"}}]
        assert diagnosis_correct(sc, plans) is ok


def test_drift_cleanup_after_heal():
    """The first plan heals but leaves junk; the agent is shown the drift and removes it."""
    rec, events = run([
        [("submit_plan", plan_args([GOOD_ROUTE, ADD_JUNK]))],
        [("submit_plan", plan_args([DEL_JUNK], fault_class="other"))],
    ])
    types = [t for t, _ in events]
    assert "drift" in types
    assert rec["drift_at_heal"] == 1 and rec["cleanup_plans"] == 1
    assert rec["outcome"] == "FIXED_VERIFIED" and rec["clean_fix"] is True
    phases = [d["phase"] for t, d in events if t == "plan_submitted"]
    assert phases == ["repair", "cleanup"]


def test_agent_may_decline_cleanup():
    rec, _ = run([[("submit_plan", plan_args([GOOD_ROUTE, ADD_JUNK]))], "DONE"])
    assert rec["outcome"] == "FIXED_VERIFIED" and rec["clean_fix"] is False and rec["residual_count"] == 1


def test_cleanup_can_be_switched_off():
    events = []
    rec = run_scenario(FakeLab(), TOPO, FLOWS, "route_missing", 0, agent="llm",
                       llm=FakeLLM([[("submit_plan", plan_args([GOOD_ROUTE, ADD_JUNK]))]]),
                       settings=load_settings("spark-1.3"), cleanup=False,
                       emit=lambda t, d: events.append(t))
    assert "drift" not in events and rec["drift_at_heal"] is None and rec["clean_fix"] is False


def _router(first_turns, second_turns):
    fakes = {"spark-open": FakeLLM(first_turns), "spark-1.3": FakeLLM(second_turns)}
    events = []
    rec = run_scenario(FakeLab(), TOPO, FLOWS, "route_missing", 0, agent="router",
                       llm_factory=lambda s: fakes[s.profile], emit=lambda t, d: events.append((t, d)))
    return rec, events, fakes


def test_router_does_not_escalate_when_the_open_model_fixes_it():
    rec, events, fakes = _router([[("submit_plan", plan_args([GOOD_ROUTE]))]], ["unused"])
    assert rec["escalated"] is False and rec["profile"] == "router" and fakes["spark-1.3"].calls == 0
    assert rec["outcome"] == "FIXED_VERIFIED" and len(rec["stages"]) == 1


def test_router_escalates_and_merges_both_attempts():
    rec, events, fakes = _router(["thinking", "still thinking", "hmm"],
                                 [[("submit_plan", plan_args([GOOD_ROUTE]))]])
    assert rec["escalated"] is True and [s["profile"] for s in rec["stages"]] == ["spark-open", "spark-1.3"]
    assert rec["outcome"] == "FIXED_VERIFIED" and rec["steps"] == 4
    assert any(t == "escalated" for t, _ in events)
    note = fakes["spark-1.3"].seen_messages[0][1]["content"]
    assert "previous automated attempt" in note
