from netproof.config import load_settings
from netproof.intent import load_intent
from netproof.runner import prepare, run_scenario
from netproof.topology import load_topology
from tests.fakes import GOOD_ROUTE, OPEN_GUEST, FakeLab, FakeLLM, plan_args

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
    assert rec["ground_truth"] == [{"device": "r-edge", "fault_class": "route_missing"}]
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
