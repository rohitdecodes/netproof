"""Command-line entry point.  Usage: python -m netproof.cli <command> [options]"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import defaultdict
from typing import List, Optional

from .config import LAB_DIR, RUNS_DIR, load_profiles
from .faults import CATALOG, FAULT_CLASSES, PHASE1_CLASSES, make_scenario
from .intent import evaluate, format_table, is_healthy, load_intent
from .records import write_record
from .runner import prepare, run_scenario
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


def _classes(spec: str) -> List[str]:
    if spec == "all":
        return FAULT_CLASSES
    if spec == "phase1":
        return PHASE1_CLASSES
    if spec == "new":
        return [c for c in FAULT_CLASSES if c not in PHASE1_CLASSES]
    return spec.split(",")


def _store():
    from .store import Store

    return Store()


def _finish(rec: dict, store=None, eval_id: Optional[str] = None, subdir: Optional[str] = None) -> str:
    """Write the JSON record and the Markdown report, and index the run in SQLite."""
    from .report import write_report

    path = write_record(rec, subdir)
    report = write_report(rec)
    (store or _store()).save_run(rec, eval_id=eval_id, record_path=str(path), report_path=str(report))
    return str(path)


# ---------------------------------------------------------------- lab commands
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


def cmd_scenarios(args) -> int:
    for c in _classes(args.classes):
        for s in range(3):
            sc = make_scenario(c, s)
            gt = ", ".join(f"{g['device']}:{g['fault_class']}" for g in sc.ground_truth)
            print(f"{sc.scenario_id:<22} {sc.variant:<20} flow={sc.reported_flow:<16} truth={gt}")
            print(f"    ticket: {sc.ticket}")
    return 0


def cmd_inject(args) -> int:
    topo, lab, flows = _lab()
    p = prepare(lab, topo, flows, args.fault, args.seed)
    print(f"scenario {p.scenario.scenario_id} ({p.scenario.variant}) injected; scope={sorted(p.ctx.scope)}")
    print(f"ticket: {p.scenario.ticket}\n")
    print(format_table(p.before))
    return 0


# ---------------------------------------------------------------- runs
def cmd_run(args) -> int:
    topo, lab, flows = _lab()
    store = _store()
    rec = run_scenario(lab, topo, flows, args.fault, args.seed, args.agent, profile=args.profile)
    path = _finish(rec, store)
    print(f"outcome={rec['outcome']} clean_fix={rec['clean_fix']} residual={rec['residual_count']} "
          f"plans={rec['plan_count']} steps={rec['steps']} cost=${rec['cost_usd']:.4f} "
          f"time={rec['wall_seconds']}s diagnosis_correct={rec['diagnosis_correct']}")
    if rec.get("error"):
        print("error:", rec["error"])
    for node, items in (rec.get("residual_items") or {}).items():
        print(f"residual on {node}: {items}")
    print(rec["final_flows"])
    print(f"record: {path}")
    return 0 if rec["outcome"] == "FIXED_VERIFIED" else 1


def summarize(records: List[dict]) -> dict:
    scored = [r for r in records if r["outcome"] != "ERROR"]
    by_class = defaultdict(list)
    for r in scored:
        by_class[r["scenario"]["fault_class"]].append(r)
    fixed = lambda rs: sum(r["outcome"] == "FIXED_VERIFIED" for r in rs)
    clean = lambda rs: sum(bool(r.get("clean_fix")) for r in rs)
    costs = [r["cost_usd"] for r in scored]
    return {
        "runs": len(records),
        "errors": len(records) - len(scored),
        "fixed_verified": fixed(scored),
        "fix_rate": round(fixed(scored) / len(scored), 3) if scored else None,
        "clean_fix_rate": round(clean(scored) / len(scored), 3) if scored else None,
        "by_class": {c: f"{fixed(rs)}/{len(rs)} fixed, {clean(rs)} clean" for c, rs in sorted(by_class.items())},
        "gate_rejections": sum(r["gate_rejections"] for r in scored),
        "collateral_rollbacks": sum(r["collateral_rollbacks"] for r in scored),
        "diagnosis_correct": sum(bool(r.get("diagnosis_correct")) for r in scored),
        "median_cost_usd": round(statistics.median(costs), 4) if costs else None,
        "total_cost_usd": round(sum(costs), 4),
        "median_seconds": statistics.median([r["wall_seconds"] for r in scored]) if scored else None,
    }


def cmd_eval(args) -> int:
    topo, lab, flows = _lab()
    store = _store()
    who = args.agent if args.agent == "baseline" else (args.profile or load_profiles().get("default", "env"))
    eval_id = f"eval-{time.strftime('%Y%m%d-%H%M%S')}-{who}" + (f"-{args.label}" if args.label else "")
    records = []
    for fault in _classes(args.faults):
        for seed in _seeds(args.seeds):
            for rep in range(args.repeats):
                try:
                    rec = run_scenario(lab, topo, flows, fault, seed, args.agent, profile=args.profile,
                                       repeat=rep)
                except Exception as e:
                    rec = {"run_id": f"{eval_id}-{fault}-s{seed}-r{rep}", "agent": args.agent,
                           "profile": args.profile, "repeat": rep,
                           "scenario": {"fault_class": fault, "seed": seed}, "outcome": "ERROR",
                           "error": f"{type(e).__name__}: {e}", "plan_count": 0, "gate_rejections": 0,
                           "collateral_rollbacks": 0, "cost_usd": 0.0, "wall_seconds": 0.0, "steps": 0}
                _finish(rec, store, eval_id=eval_id, subdir=eval_id)
                records.append(rec)
                print(f"{fault:<18} seed={seed:<3} rep={rep} -> {rec['outcome']:<24} "
                      f"clean={rec.get('clean_fix')} ${rec.get('cost_usd', 0):.4f} {rec.get('wall_seconds', 0)}s")
    summary = summarize(records)
    summary["eval_id"] = eval_id
    (RUNS_DIR / eval_id).mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / eval_id / "summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))
    return 0


def cmd_scoreboard(args) -> int:
    store = _store()
    evals = args.eval or [e["eval_id"] for e in store.evals()]
    rows = store.scoreboard(evals)
    print(f"evals: {', '.join(evals) or '(none)'}\n")
    print(f"{'agent':<9} {'profile':<11} {'runs':>4} {'fix':>6} {'clean':>6} {'diag':>6} "
          f"{'collat':>6} {'gate':>5} {'med $':>7} {'med s':>6}")
    for r in rows:
        f = lambda v: "-" if v is None else v
        print(f"{r['agent']:<9} {r['profile']:<11} {r['runs']:>4} {f(r['fix_rate']):>6} "
              f"{f(r['clean_fix_rate']):>6} {f(r['diagnosis_rate']):>6} {r['collateral_rollbacks']:>6} "
              f"{r['gate_rejections']:>5} {f(r['median_cost_usd']):>7} {f(r['median_seconds']):>6}")
        print(f"    by class: {r['by_class']}")
    return 0


def cmd_report(args) -> int:
    from .report import write_report

    files = list(RUNS_DIR.glob(f"**/{args.run}.json"))
    if not files:
        print(f"no record named {args.run}.json under runs/")
        return 1
    rec = json.loads(files[0].read_text())
    print(write_report(rec))
    return 0


def cmd_serve(args) -> int:
    import uvicorn

    uvicorn.run("netproof.server:create_app", factory=True, host=args.host, port=args.port, log_level="info")
    return 0


# ---------------------------------------------------------------- validation
def cmd_validate_lab(args) -> int:
    """Reset + inject N times across all classes: reset time and post-injection check."""
    topo, lab, flows = _lab()
    times, failures = [], 0
    for i in range(args.n):
        fault = FAULT_CLASSES[i % len(FAULT_CLASSES)]
        t = time.monotonic()
        lab.reset()
        times.append(time.monotonic() - t)
        try:
            prepare(lab, topo, flows, fault, i)
        except RuntimeError as e:
            failures += 1
            print(f"run {i} ({fault}): {e}")
    lab.reset()
    print(f"reset seconds: median={statistics.median(times):.1f} max={max(times):.1f}")
    print(f"post-injection checks passed: {args.n - failures}/{args.n}")
    return 0 if failures == 0 and max(times) <= 15 else 1


def cmd_validate_verifier(args) -> int:
    """Reference fixes commit, heal and leave zero residual; bad fixes roll back to identical state."""
    from .executor import Executor, PlanOutcome
    from .minimality import residual, residual_count

    topo, lab, flows = _lab()
    ex = Executor(lab, flows)
    fix_ok = fix_total = bad_ok = bad_total = 0
    for fault in _classes(args.faults):
        for idx, v in enumerate(CATALOG[fault]):
            # reference fixes, applied in order
            p = prepare(lab, topo, flows, fault, idx)
            before, outcomes = p.before, []
            for plan_dict in v.fixes:
                d = dict(plan_dict, commands=[lab.resolve_placeholders(plan_dict["device"], c)
                                              for c in plan_dict["commands"]])
                res = ex.execute(ChangePlan(**d), p.ctx, before=before)
                outcomes.append(res.outcome.value)
                if res.gate_violations:
                    print("   gate:", res.gate_violations)
                before = evaluate(lab, flows)
            healthy = is_healthy(before)
            res_items = residual(p.golden, {n: lab.snapshot(n) for n in topo.nodes})
            ok = all(o == PlanOutcome.COMMITTED.value for o in outcomes) and healthy and not res_items
            fix_total += 1
            fix_ok += ok
            print(f"{v.key:<22} fix     -> {outcomes} healthy={healthy} residual={residual_count(res_items)} "
                  f"{'PASS' if ok else 'FAIL'}")
            if res_items:
                print("   residual:", res_items)
            # bad fix
            if v.bad_fix:
                p = prepare(lab, topo, flows, fault, idx)
                bd = dict(v.bad_fix, commands=[lab.resolve_placeholders(v.bad_fix["device"], c)
                                               for c in v.bad_fix["commands"]])
                res = ex.execute(ChangePlan(**bd), p.ctx, before=p.before)
                ok = res.outcome == PlanOutcome.ROLLED_BACK_COLLATERAL and res.restored_ok
                bad_total += 1
                bad_ok += ok
                print(f"{v.key:<22} bad_fix -> {res.outcome.value:<24} regressions={res.regressions} "
                      f"restored_ok={res.restored_ok} {'PASS' if ok else 'FAIL'}")
                if res.gate_violations:
                    print("   gate:", res.gate_violations)
    lab.reset()
    print(f"\nreference fixes committed, healthy and clean: {fix_ok}/{fix_total}")
    print(f"bad fixes detected and rolled back with identical state: {bad_ok}/{bad_total}")
    return 0 if fix_ok == fix_total and bad_ok == bad_total else 1


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="netproof")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("lab-up").set_defaults(fn=cmd_lab_up)
    sub.add_parser("lab-down").set_defaults(fn=cmd_lab_down)
    sub.add_parser("provision").set_defaults(fn=cmd_provision)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sp = sub.add_parser("scenarios")
    sp.add_argument("--classes", default="all", help="all | phase1 | new | comma list")
    sp.set_defaults(fn=cmd_scenarios)
    for name, fn in (("inject", cmd_inject), ("run", cmd_run)):
        sp = sub.add_parser(name)
        sp.add_argument("--fault", required=True, choices=FAULT_CLASSES)
        sp.add_argument("--seed", type=int, default=0)
        if name == "run":
            sp.add_argument("--agent", choices=["llm", "baseline"], default="llm")
            sp.add_argument("--profile", default=None, help="model profile from models.yaml")
        sp.set_defaults(fn=fn)
    ev = sub.add_parser("eval")
    ev.add_argument("--agent", choices=["llm", "baseline"], default="llm")
    ev.add_argument("--profile", default=None)
    ev.add_argument("--faults", default="all", help="all | phase1 | new | comma list")
    ev.add_argument("--seeds", default="0-2")
    ev.add_argument("--repeats", type=int, default=1)
    ev.add_argument("--label", default="")
    ev.set_defaults(fn=cmd_eval)
    sb = sub.add_parser("scoreboard")
    sb.add_argument("--eval", action="append", help="eval id; repeat for several; default all")
    sb.set_defaults(fn=cmd_scoreboard)
    rp = sub.add_parser("report")
    rp.add_argument("--run", required=True, help="run id (record file name without .json)")
    rp.set_defaults(fn=cmd_report)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(fn=cmd_serve)
    vl = sub.add_parser("validate-lab")
    vl.add_argument("--n", type=int, default=27)
    vl.set_defaults(fn=cmd_validate_lab)
    vv = sub.add_parser("validate-verifier")
    vv.add_argument("--faults", default="all")
    vv.set_defaults(fn=cmd_validate_verifier)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
