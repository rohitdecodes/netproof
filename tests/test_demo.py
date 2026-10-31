"""Seeded safety demonstrations, on the fake lab."""
from netproof.demo import GATE_DEMO_COMMANDS, run_seeded, seeded_plan
from netproof.faults import get_variant
from netproof.intent import load_intent
from netproof.topology import load_topology
from tests.fakes import FakeLab

TOPO = load_topology()
FLOWS = load_intent()


def _run(kind):
    events = []
    lab = FakeLab()
    rec = run_seeded(lab, TOPO, FLOWS, "route_missing", 0, kind, emit=lambda t, d: events.append((t, d)))
    return rec, events, lab


def test_seeded_bad_fix_is_rolled_back_and_policy_holds():
    rec, events, lab = _run("bad_fix")
    assert rec["outcome"] == "ROLLED_BACK_COLLATERAL" and rec["collateral_rollbacks"] == 1
    assert rec["policy_intact"] is True and rec["agent"] == "seeded" and rec["cost_usd"] == 0.0
    result = rec["plans"][0]["result"]
    assert result["restored_ok"] and result["regressions"]
    types = [t for t, _ in events]
    assert types[0] == "run_started" and types[-1] == "run_finished" and "plan_result" in types
    assert lab.state == {"route_ok": True, "guest_open": False, "junk": False}  # reset at the end


def test_seeded_gate_demo_is_refused_before_anything_runs():
    rec, events, lab = _run("gate")
    assert rec["outcome"] == "REJECTED_BY_GATE" and rec["gate_rejections"] == 1
    assert not any(c in lab.commands for c in GATE_DEMO_COMMANDS)


def test_seeded_plan_requires_a_bad_fix():
    import pytest

    v = get_variant("wrong_gateway.a")
    if v.bad_fix is None:
        with pytest.raises(ValueError):
            seeded_plan(v, "bad_fix")
    assert seeded_plan(v, "gate")["commands"] == GATE_DEMO_COMMANDS
