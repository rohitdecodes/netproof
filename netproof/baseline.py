"""Scripted non-AI baseline: a fixed runbook that knows the network diagram.

It uses the same gate and executor as the agent, so the comparison is fair.
If this script solves most scenarios, the faults are too easy to show what the model adds.
"""
from __future__ import annotations

import ipaddress
import shlex
import time
from typing import Callable, List, Optional

from .executor import Executor
from .faults import Scenario
from .gate import GateContext
from .intent import Flow, evaluate, format_table, is_healthy
from .schemas import ChangePlan
from .topology import Topology


class BaselineRunner:
    def __init__(self, lab, topo: Topology, flows: List[Flow], scenario: Scenario, gate_ctx: GateContext,
                 emit: Optional[Callable[[str, dict], None]] = None):
        self.lab = lab
        self.topo = topo
        self.flows = {f.id: f for f in flows}
        self.flow_list = flows
        self.scenario = scenario
        self.ctx = gate_ctx
        self.executor = Executor(lab, flows)
        self.plans: List[dict] = []
        self.emit = emit or (lambda _t, _d: None)

    def _try(self, device: str, commands: List[str], why: str) -> bool:
        if not commands:
            return False
        plan = ChangePlan(device=device, commands=commands, rationale=why,
                          expected_effect="restore reported flow", rollback=["(snapshot restore)"])
        index = len(self.plans)
        self.emit("plan_submitted", {"index": index, "step": index + 1, "plan": plan.model_dump(), "root_cause": None})
        res = self.executor.execute(plan, self.ctx)
        self.emit("plan_result", {"index": index, **res.to_dict()})
        self.plans.append({"index": index, "plan": plan.model_dump(), "root_cause": None,
                           "result": res.to_dict()})
        return res.healthy_after

    def _router_on(self, network: str) -> str:
        for n in self.topo.network_members(network):
            if self.topo.nodes[n].is_router:
                return n
        raise ValueError(f"no router on {network}")

    def run(self) -> dict:
        t0 = time.monotonic()
        target = self.flows[self.scenario.reported_flow]
        path = self.topo.path_nodes(target.src, target.dst)
        done = False

        # 1. Hosts on the path: default gateway must be the router on their subnet.
        for host in (target.src, target.dst):
            if done:
                break
            net = next(iter(self.topo.nodes[host].interfaces))
            want = self.topo.nodes[self._router_on(net)].interfaces[net]
            have = next((r["gateway"] for r in self.lab.routes(host) if r["dst"] == "default"), None)
            if have != want:
                done = self._try(host, [f"ip route replace default via {want}"], "fix default gateway")

        # 2. Routers on the path: interfaces up, then a route to every non-connected subnet.
        for r in sorted(n for n in path if self.topo.nodes[n].is_router):
            if done:
                break
            cmds = [f"ip link set {ifname} up" for ifname, up in self.lab.link_states(r).items() if not up]
            connected = set(self.topo.nodes[r].interfaces)
            have = {rt["dst"] for rt in self.lab.routes(r)}
            peer = next(p for p in self.topo.neighbors(r) if self.topo.nodes[p].is_router)
            shared = next(n for n in self.topo.nodes[peer].interfaces if n in connected)
            next_hop = self.topo.nodes[peer].interfaces[shared]
            for net, spec in self.topo.networks.items():
                if net in connected or spec["subnet"] in have:
                    continue
                cmds.append(f"ip route replace {spec['subnet']} via {next_hop}")
            done = self._try(r, cmds[:5], "interfaces up and missing routes")

        # 3. Routers on the path: delete DROP rules that match the reported flow.
        src_ip = ipaddress.ip_address(self.topo.resolve(target.src))
        dst_ip = ipaddress.ip_address(self.topo.resolve(target.dst))
        for r in sorted(n for n in path if self.topo.nodes[n].is_router):
            if done:
                break
            cmds = []
            for line in self.lab.exec(r, ["iptables", "-S", "FORWARD"]).out.splitlines():
                tok = shlex.split(line)
                if tok[:2] != ["-A", "FORWARD"] or tok[-2:] != ["-j", "DROP"]:
                    continue
                opts = dict(zip(tok[2::2], tok[3::2]))
                s_ok = "-s" not in opts or src_ip in ipaddress.ip_network(opts["-s"], strict=False)
                d_ok = "-d" not in opts or dst_ip in ipaddress.ip_network(opts["-d"], strict=False)
                port_ok = "--dport" not in opts or (target.port and int(opts["--dport"]) == target.port)
                if s_ok and d_ok and port_ok:
                    cmds.append("iptables -D FORWARD " + " ".join(shlex.quote(t) for t in tok[2:]))
            done = self._try(r, cmds[:5], "remove DROP rules matching the reported flow")

        final = evaluate(self.lab, self.flow_list)
        healthy = is_healthy(final)
        return {
            "agent": "baseline",
            "model": None,
            "scenario": self.scenario.__dict__,
            "outcome": "FIXED_VERIFIED" if healthy else (
                self.plans[-1]["result"]["outcome"] if self.plans else "BUDGET_EXHAUSTED"),
            "error": None,
            "steps": len(self.plans),
            "plans": self.plans,
            "plan_count": len(self.plans),
            "gate_rejections": sum(p["result"]["outcome"] == "REJECTED_BY_GATE" for p in self.plans),
            "collateral_rollbacks": sum(p["result"]["outcome"] == "ROLLED_BACK_COLLATERAL" for p in self.plans),
            "root_cause": None,
            "diagnosis_correct": None,
            "usage": {"prompt": 0, "completion": 0, "cached": 0},
            "cost_usd": 0.0,
            "wall_seconds": round(time.monotonic() - t0, 1),
            "final_flows": format_table(final),
        }
