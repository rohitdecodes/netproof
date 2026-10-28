"""Command-line entry point.  Usage: python -m netproof.cli <command> [options]"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from typing import List

from .config import LAB_DIR, RUNS_DIR, load_settings
from .faults import CATALOG, FAULT_CLASSES, make_scenario
from .gate import build_context
from .intent import evaluate, format_table, is_healthy, load_intent
from .records import new_run_id, write_record
from .schemas import ChangePlan
from .topology import load_topology

COMPOSE = ["docker", "compose", "-f", str(LAB_DIR / "docker-compose.yml")]


def _lab():
    from .lab import DockerLab

    topo = load_topology()
    return topo, DockerLab(topo), load_intent()


def _seeds(spec: str) -> List[int]:
    out: List[int] = []
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def _prepare(lab, topo, flows, fault: str, seed: int):
    """Reset, inject, and confirm the fault took effect. Returns (scenario, results)."""
    sc = make_scenario(fault, seed)
    lab.reset()
    for cmd in sc.inject:
        r = lab.run_command(sc.device, lab.resolve_placeholders(sc.device, cmd))
        if not r.ok:
            raise RuntimeError(f"injection failed on {sc.device}: {cmd}: {r.text()}")
    results = evaluate(lab, flows)
    if results[sc.reported_flow].ok:
        raise RuntimeError(f"post-injection check failed: {sc.reported_flow} still matches intent")
    return sc, results


# ---------------------------------------------------------------- commands
def cmd_lab_up(_args) -> int:
    subprocess.run(COMPOSE + ["up", "-d"], check=True)
    time.sleep(2)
    return cmd_check(None, provision=True)


def cmd_lab_down(_args) -> int:
    return subprocess.run(COMPOSE + ["down"]).returncode


def cmd_provision(_args) -> int:
    topo, lab, flows = _lab()
    t = time.monotonic()
    lab.provision_all()
    print(f"provisioned {len(topo.nodes)} nodes in {time.monotonic() - t:.1f}s")
    return 0


def cmd_check(_args, provision: bool = False) -> int:
    topo, lab, flows = _lab()
    if provision:
        lab.provision_all()
    res = evaluate(lab, flows)
    print(format_table(res))
    ok = is_healthy(res)
    print("\nHEALTHY" if ok else "\nNOT HEALTHY")
    return 0 if ok else 1


def cmd_scenarios(_args) -> int:
    for c in FAULT_CLASSES:
        for s in range(3):
            sc = make_scenario(c, s)
            print(f"{sc.scenario_id:<20} {sc.variant:<18} device={sc.device:<11} flow={sc.reported_flow}")
            print(f"    ticket: {sc.ticket}")
    return 0


def cmd_inject(args) -> int:
    topo, lab, flows = _lab()
    sc, res = _prepare(lab, topo, flows, args.fault, args.seed)
    print(f"scenario {sc.scenario_id} ({sc.variant}) injected on {sc.device}")
    print(f"ticket: {sc.ticket}\n")
    print(format_table(res))
    return 0


def _run_one(lab, topo, flows, fault: str, seed: int, agent: str, repeat: int = 0) -> dict:
    sc, _ = _prepare(lab, topo, flows, fault, seed)
    target = next(f for f in flows if f.id == sc.reported_flow)
    ctx = build_context(topo, lab, target.src, target.dst)
    if agent == "baseline":
        from .baseline import BaselineRunner

        rec = BaselineRunner(lab, topo, flows, sc, ctx).run()
    else:
        from .agent import AgentRunner
        from .llm import LLMClient

        s = load_settings()
        rec = AgentRunner(LLMClient(s), lab, topo, flows, s, sc, ctx).run()
    rec["run_id"] = new_run_id(agent, sc.scenario_id, repeat)
    rec["repeat"] = repeat
    return rec


def cmd_run(args) -> int:
    topo, lab, flows = _lab()
    rec = _run_one(lab, topo, flows, args.fault, args.seed, args.agent)
    path = write_record(rec)
    print(f"outcome={rec['outcome']} plans={rec['plan_count']} steps={rec['steps']} "
          f"cost=${rec['cost_usd']:.4f} time={rec['wall_seconds']}s diagnosis_correct={rec['diagnosis_correct']}")
    if rec.get("error"):
        print("error:", rec["error"])
    print(rec["final_flows"])
    print(f"record: {path}")
    return 0 if rec["outcome"] == "FIXED_VERIFIED" else 1


def summarize(records: List[dict]) -> dict:
    scored = [r for r in records if r["outcome"] != "ERROR"]
    by_class = defaultdict(list)
    for r in scored:
        by_class[r["scenario"]["fault_class"]].append(r)
    fixed = lambda rs: sum(r["outcome"] == "FIXED_VERIFIED" for r in rs)
    costs = [r["cost_usd"] for r in scored]
    return {
        "runs": len(records),
        "errors": len(records) - len(scored),
        "fixed_verified": fixed(scored),
        "fix_rate": round(fixed(scored) / len(scored), 3) if scored else None,
        "by_class": {c: f"{fixed(rs)}/{len(rs)}" for c, rs in sorted(by_class.items())},
        "gate_rejections": sum(r["gate_rejections"] for r in scored),
        "collateral_rollbacks": sum(r["collateral_rollbacks"] for r in scored),
        "diagnosis_correct": sum(bool(r.get("diagnosis_correct")) for r in scored),
        "median_cost_usd": round(statistics.median(costs), 4) if costs else None,
        "total_cost_usd": round(sum(costs), 4),
        "median_seconds": statistics.median([r["wall_seconds"] for r in scored]) if scored else None,
    }


def cmd_eval(args) -> int:
    topo, lab, flows = _lab()
    faults = FAULT_CLASSES if args.faults == "all" else args.faults.split(",")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    sub = f"eval-{stamp}-{args.agent}"
    records = []
    for fault in faults:
        for seed in _seeds(args.seeds):
            for rep in range(args.repeats):
                try:
                    rec = _run_one(lab, topo, flows, fault, seed, args.agent, rep)
                except Exception as e:
                    rec = {"run_id": new_run_id(args.agent, f"{fault}-s{seed}", rep), "agent": args.agent,
                           "scenario": {"fault_class": fault, "seed": seed}, "outcome": "ERROR",
                           "error": f"{type(e).__name__}: {e}", "plan_count": 0, "gate_rejections": 0,
                           "collateral_rollbacks": 0, "cost_usd": 0.0, "wall_seconds": 0.0}
                write_record(rec, sub)
                records.append(rec)
                print(f"{fault:<15} seed={seed:<3} rep={rep} -> {rec['outcome']:<24} "
                      f"${rec.get('cost_usd', 0):.4f} {rec.get('wall_seconds', 0)}s")
    summary = summarize(records)
    (RUNS_DIR / sub / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def cmd_validate_lab(args) -> int:
    """V1: reset + inject N times; reset time and post-injection check."""
    topo, lab, flows = _lab()
    times, failures = [], 0
    for i in range(args.n):
        fault = FAULT_CLASSES[i % len(FAULT_CLASSES)]
        t = time.monotonic()
        lab.reset()
        times.append(time.monotonic() - t)
        try:
            _prepare(lab, topo, flows, fault, i)
        except RuntimeError as e:
            failures += 1
            print(f"run {i}: {e}")
    lab.reset()
    print(f"V1 reset seconds: median={statistics.median(times):.1f} max={max(times):.1f}")
    print(f"V1 post-injection checks passed: {args.n - failures}/{args.n}")
    return 0 if failures == 0 and max(times) <= 15 else 1


def cmd_validate_verifier(_args) -> int:
    """V3 plus fix sanity: correct fixes commit and heal; bad fixes roll back and restore state."""
    from .executor import Executor, PlanOutcome

    topo, lab, flows = _lab()
    ex = Executor(lab, flows)
    good, bad, bad_total = 0, 0, 0
    total = 0
    for fault, variants in CATALOG.items():
        for idx, v in enumerate(variants):
            for kind, plan_dict in (("fix", v.fix), ("bad_fix", v.bad_fix)):
                if plan_dict is None:
                    continue
                sc, before = _prepare(lab, topo, flows, fault, idx)
                assert sc.variant == v.key
                target = next(f for f in flows if f.id == sc.reported_flow)
                ctx = build_context(topo, lab, target.src, target.dst)
                d = dict(plan_dict)
                d["commands"] = [lab.resolve_placeholders(v.device, c) for c in d["commands"]]
                res = ex.execute(ChangePlan(**d), ctx, before=before)
                if kind == "fix":
                    total += 1
                    ok = res.outcome == PlanOutcome.COMMITTED and res.healthy_after
                    good += ok
                else:
                    bad_total += 1
                    ok = res.outcome == PlanOutcome.ROLLED_BACK_COLLATERAL and res.restored_ok
                    bad += ok
                print(f"{v.key:<18} {kind:<8} -> {res.outcome.value:<24} "
                      f"regressions={res.regressions} restored_ok={res.restored_ok} {'PASS' if ok else 'FAIL'}")
                if res.gate_violations:
                    print("   gate:", res.gate_violations)
    lab.reset()
    print(f"\ncorrect fixes committed and healthy: {good}/{total}")
    print(f"V3 bad fixes detected and rolled back with identical state: {bad}/{bad_total}")
    return 0 if good == total and bad == bad_total else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="netproof")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lab-up").set_defaults(fn=cmd_lab_up)
    sub.add_parser("lab-down").set_defaults(fn=cmd_lab_down)
    sub.add_parser("provision").set_defaults(fn=cmd_provision)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("scenarios").set_defaults(fn=cmd_scenarios)
    for name, fn in (("inject", cmd_inject), ("run", cmd_run)):
        sp = sub.add_parser(name)
        sp.add_argument("--fault", required=True, choices=FAULT_CLASSES)
        sp.add_argument("--seed", type=int, default=0)
        if name == "run":
            sp.add_argument("--agent", choices=["llm", "baseline"], default="llm")
        sp.set_defaults(fn=fn)
    ev = sub.add_parser("eval")
    ev.add_argument("--agent", choices=["llm", "baseline"], default="llm")
    ev.add_argument("--faults", default="all")
    ev.add_argument("--seeds", default="0-4")
    ev.add_argument("--repeats", type=int, default=1)
    ev.set_defaults(fn=cmd_eval)
    vl = sub.add_parser("validate-lab")
    vl.add_argument("--n", type=int, default=20)
    vl.set_defaults(fn=cmd_validate_lab)
    sub.add_parser("validate-verifier").set_defaults(fn=cmd_validate_verifier)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
