from netproof.agent import AgentRunner
from netproof.config import load_settings
from netproof.faults import make_scenario
from netproof.gate import GateContext
from netproof.intent import load_intent
from netproof.topology import load_topology
from tests.fakes import GOOD_ROUTE, OPEN_GUEST, FakeLab, FakeLLM, plan_args

TOPO = load_topology()
FLOWS = load_intent()
SC = make_scenario("route_missing", 0)  # r-edge lost its route to the server subnet
CTX = GateContext(devices=set(TOPO.nodes), scope=TOPO.path_nodes("pc-staff", "fileserver"),
                  ifaces={n: {"eth0", "eth1", "eth2"} for n in TOPO.nodes}, node_ips=TOPO.node_ips())


def run(turns):
    lab = FakeLab()
    llm = FakeLLM(turns)
    rec = AgentRunner(llm, lab, TOPO, FLOWS, load_settings(), SC, CTX).run()
    return rec, llm, lab


def test_investigate_then_fix():
    rec, llm, _ = run([
        [("show_routes", {"device": "r-edge"})],
        [("submit_plan", plan_args([GOOD_ROUTE]))],
    ])
    assert rec["outcome"] == "FIXED_VERIFIED"
    assert rec["diagnosis_correct"] is True
    assert rec["steps"] == 2 and rec["plan_count"] == 1
    # the tool result was sent back with the right id
    last = llm.seen_messages[-1][-1]
    assert last["role"] == "tool" and last["tool_call_id"] == "call_1_0"


def test_collateral_then_correct_fix():
    rec, _, _ = run([
        [("submit_plan", plan_args([GOOD_ROUTE, OPEN_GUEST]))],
        [("submit_plan", plan_args([GOOD_ROUTE]))],
    ])
    assert rec["outcome"] == "FIXED_VERIFIED"
    assert rec["collateral_rollbacks"] == 1


def test_gate_rejection_is_reported_back():
    rec, llm, lab = run([
        [("submit_plan", plan_args(["iptables -F"]))],
        [("submit_plan", plan_args([GOOD_ROUTE]))],
    ])
    assert rec["gate_rejections"] == 1 and rec["outcome"] == "FIXED_VERIFIED"
    tool_msg = llm.seen_messages[1][-1]["content"]
    assert tool_msg.startswith("REJECTED BY POLICY GATE")
    assert "iptables -F" not in lab.commands


def test_bad_json_arguments_do_not_crash():
    rec, llm, _ = run([
        [("show_routes", "{not json")],
        [("submit_plan", plan_args([GOOD_ROUTE]))],
    ])
    assert rec["outcome"] == "FIXED_VERIFIED"
    assert "not valid JSON" in llm.seen_messages[1][-1]["content"]


def test_model_that_never_acts_runs_out():
    rec, _, _ = run(["thinking...", "still thinking", "hmm"])
    assert rec["outcome"] == "BUDGET_EXHAUSTED" and rec["steps"] == 3


def test_plan_limit_stops_the_run():
    bad = plan_args(["ip route del 10.10.1.0/24"])  # fake lab errors on this -> no effect
    rec, _, _ = run([[("submit_plan", bad)]] * 5)
    assert rec["plan_count"] == 3
    assert rec["outcome"] == "ROLLED_BACK_NO_EFFECT"
