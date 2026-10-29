"""Run orchestration shared by the CLI and the dashboard server.

prepare(): reset the lab, take golden snapshots, inject the scenario, confirm it broke something.
run_scenario(): prepare, run the agent or the baseline, measure residual damage, return the record.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from .config import Settings, load_settings
from .faults import Scenario, make_scenario
from .gate import GateContext, build_context
from .intent import Flow, Results, evaluate, failing
from .minimality import residual, residual_count
from .topology import Topology

Emit = Callable[[str, dict], None]


def _no_emit(_t: str, _d: dict) -> None:
    return None


def new_run_id(agent: str, scenario_id: str, repeat: int = 0, profile: Optional[str] = None) -> str:
    who = agent if agent == "baseline" else (profile or agent)
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{who}-{scenario_id}-r{repeat}"


@dataclass
class Prepared:
    scenario: Scenario
    before: Results
    golden: Dict[str, dict]
    ctx: GateContext


def flows_payload(results: Results) -> Dict[str, bool]:
    return {fid: r.ok for fid, r in results.items()}


def prepare(lab, topo: Topology, flows: List[Flow], fault: str, seed: int) -> Prepared:
    sc = make_scenario(fault, seed)
    lab.reset()
    golden = {n: lab.snapshot(n) for n in topo.nodes}
    for device, cmd in sc.injections:
        r = lab.run_command(device, lab.resolve_placeholders(device, cmd))
        if not r.ok:
            raise RuntimeError(f"injection failed on {device}: {cmd}: {r.text()}")
    before = evaluate(lab, flows)
    if before[sc.reported_flow].ok:
        raise RuntimeError(f"post-injection check failed: {sc.reported_flow} still matches intent")
    broken = [r.flow for r in failing(before)]
    ctx = build_context(topo, lab, broken)
    return Prepared(sc, before, golden, ctx)


def run_scenario(lab, topo: Topology, flows: List[Flow], fault: str, seed: int, agent: str = "llm",
                 profile: Optional[str] = None, repeat: int = 0, emit: Optional[Emit] = None,
                 run_id: Optional[str] = None, llm=None, settings: Optional[Settings] = None) -> dict:
    emit = emit or _no_emit
    settings = settings or (load_settings(profile) if agent == "llm" else None)
    p = prepare(lab, topo, flows, fault, seed)
    sc = p.scenario
    run_id = run_id or new_run_id(agent, sc.scenario_id, repeat, settings.profile if settings else None)
    emit("run_started", {"run_id": run_id, "agent": agent,
                         "profile": settings.profile if settings else None,
                         "model": settings.model if settings else None,
                         "scenario_id": sc.scenario_id, "fault_class": sc.fault_class, "seed": seed,
                         "ticket": sc.ticket, "reported_flow": sc.reported_flow,
                         "scope": sorted(p.ctx.scope)})
    emit("flows", {"stage": "before", "flows": flows_payload(p.before)})

    if agent == "baseline":
        from .baseline import BaselineRunner

        rec = BaselineRunner(lab, topo, flows, sc, p.ctx, emit=emit).run()
    else:
        from .agent import AgentRunner

        if llm is None:
            from .llm import LLMClient

            llm = LLMClient(settings)
        rec = AgentRunner(llm, lab, topo, flows, settings, sc, p.ctx, emit=emit).run()

    if rec.get("outcome") != "ERROR":
        final = {n: lab.snapshot(n) for n in topo.nodes}
        res = residual(p.golden, final)
        rec["residual_items"] = res
        rec["residual_count"] = residual_count(res)
    else:
        rec["residual_items"], rec["residual_count"] = {}, None
    rec["clean_fix"] = rec["outcome"] == "FIXED_VERIFIED" and rec["residual_count"] == 0
    rec["run_id"] = run_id
    rec["repeat"] = repeat
    rec["ground_truth"] = sc.ground_truth
    rec["flows_before"] = flows_payload(p.before)
    if "final_flow_ok" not in rec and rec.get("outcome") != "ERROR":
        rec["final_flow_ok"] = flows_payload(evaluate(lab, flows))
    emit("flows", {"stage": "final", "flows": rec.get("final_flow_ok", {})})
    emit("run_finished", {k: rec.get(k) for k in (
        "outcome", "plan_count", "steps", "cost_usd", "wall_seconds", "diagnosis_correct",
        "clean_fix", "residual_count", "residual_items", "ground_truth", "gate_rejections",
        "collateral_rollbacks", "error")})
    return rec
