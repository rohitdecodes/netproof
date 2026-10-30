from netproof.executor import Executor, PlanOutcome
from netproof.gate import GateContext
from netproof.intent import load_intent
from netproof.schemas import ChangePlan
from netproof.topology import load_topology
from tests.fakes import GOOD_ROUTE, OPEN_GUEST, FakeLab

TOPO = load_topology()
FLOWS = load_intent()
CTX = GateContext(devices=set(TOPO.nodes), scope=TOPO.path_nodes("pc-staff", "fileserver"),
                  ifaces={n: {"eth0", "eth1", "eth2"} for n in TOPO.nodes}, node_ips=TOPO.node_ips())


def plan(cmds):
    return ChangePlan(device="r-edge", commands=cmds, rationale="r", expected_effect="e", rollback=["x"])


def test_correct_fix_commits_and_heals():
    lab = FakeLab()
    res = Executor(lab, FLOWS).execute(plan([GOOD_ROUTE]), CTX)
    assert res.outcome == PlanOutcome.COMMITTED and res.healthy_after
    assert lab.state["route_ok"]


def test_fix_that_opens_guest_is_rolled_back_and_state_restored():
    lab = FakeLab()
    res = Executor(lab, FLOWS).execute(plan([GOOD_ROUTE, OPEN_GUEST]), CTX)
    assert res.outcome == PlanOutcome.ROLLED_BACK_COLLATERAL
    assert res.restored_ok is True
    assert lab.state == {"route_ok": False, "guest_open": False, "junk": False}
    assert "guest_staff_ping" in res.regressions


def test_command_error_rolls_back():
    lab = FakeLab()
    res = Executor(lab, FLOWS).execute(plan(["ip route del 10.10.1.0/24"]), CTX)
    assert res.outcome == PlanOutcome.ROLLED_BACK_NO_EFFECT
    assert res.apply_errors and res.restored_ok


def test_gate_rejection_changes_nothing():
    lab = FakeLab()
    res = Executor(lab, FLOWS).execute(plan(["iptables -F"]), CTX)
    assert res.outcome == PlanOutcome.REJECTED_BY_GATE
    assert lab.commands == []


def test_cleanup_rule_keeps_a_change_that_reduces_drift():
    from tests.fakes import DEL_JUNK

    lab = FakeLab(route_ok=True)
    lab.state["junk"] = True
    drift = lambda: {"r-edge": ["rule extra: junk"]} if lab.state["junk"] else {}
    res = Executor(lab, FLOWS, drift_fn=drift).execute(plan([DEL_JUNK]), CTX)
    assert res.cleanup and res.outcome == PlanOutcome.COMMITTED
    assert (res.drift_before, res.drift_after) == (1, 0) and not lab.state["junk"]


def test_cleanup_rule_rolls_back_a_change_that_does_not_reduce_drift():
    from tests.fakes import ADD_JUNK

    lab = FakeLab(route_ok=True)
    drift = lambda: {"r-edge": ["rule extra: junk"]} if lab.state["junk"] else {}
    res = Executor(lab, FLOWS, drift_fn=drift).execute(plan([ADD_JUNK]), CTX)
    assert res.cleanup and res.outcome == PlanOutcome.ROLLED_BACK_NO_EFFECT
    assert not lab.state["junk"] and res.restored_ok
