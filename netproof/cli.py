"""Command-line entry point.  Usage: python -m netproof.cli <command> [options]"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from typing import List, Optional

from .config import LAB_DIR, RUNS_DIR, load_profiles
from .faults import PHASE1_CLASSES, SPLITS, classes_for, make_scenario
from .intent import evaluate, format_table, is_healthy, load_intent
from .records import write_record
from .runner import prepare, run_scenario
from .schemas import ChangePlan
from .store import pending_jobs
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


def _classes(spec: str, split: str = "dev") -> List[str]:
    known = classes_for(split)
    if spec == "all":
        return known
    if spec == "phase1":
        return [c for c in PHASE1_CLASSES if c in known]
    if spec == "new":
        return [c for c in known if c not in PHASE1_CLASSES]
    wanted = spec.split(",")
    bad = [c for c in wanted if c not in known]
    if bad:
        raise SystemExit(f"unknown classes for split {split}: {bad}; known: {known}")
    return wanted


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
    for c in _classes(args.classes, args.split):
        for s in range(3):
            sc = make_scenario(c, s, args.split)
            gt = ", ".join(f"{g['device']}:{g['fault_class']}" for g in sc.ground_truth)
            print(f"{sc.scenario_id:<22} {sc.variant:<20} flow={sc.reported_flow:<16} truth={gt}")
            print(f"    ticket: {sc.ticket}")
    return 0


def cmd_inject(args) -> int:
    topo, lab, flows = _lab()
    p = prepare(lab, topo, flows, args.fault, args.seed, args.split)
    print(f"scenario {p.scenario.scenario_id} ({p.scenario.variant}) injected; scope={sorted(p.ctx.scope)}")
    print(f"ticket: {p.scenario.ticket}\n")
    print(format_table(p.before))
    return 0


# ---------------------------------------------------------------- runs
def cmd_run(args) -> int:
    if not freeze_guard(args.split, args.agent, args.allow_unfrozen):
        return 2
    topo, lab, flows = _lab()
    store = _store()
    rec = run_scenario(lab, topo, flows, args.fault, args.seed, args.agent, profile=args.profile,
                       split=args.split, cleanup=not args.no_cleanup)
    path = _finish(rec, store)
    print(f"outcome={rec['outcome']} clean_fix={rec['clean_fix']} residual={rec['residual_count']} "
          f"plans={rec['plan_count']} steps={rec['steps']} cost=${rec['cost_usd']:.4f} "
          f"time={rec['wall_seconds']}s diagnosis_correct={rec['diagnosis_correct']}")
    print(f"unsafe_attempts={rec['unsafe_attempts']} trap_hits={rec['trap_hits']} "
          f"policy_intact={rec['policy_intact']} escalated={rec['escalated']} drift_at_heal={rec.get('drift_at_heal')}")
    if rec.get("error"):
        print("error:", rec["error"])
    for node, items in (rec.get("residual_items") or {}).items():
        print(f"residual on {node}: {items}")
    print(rec["final_flows"])
    print(f"record: {path}")
    return 0 if rec["outcome"] == "FIXED_VERIFIED" else 1


def preflight(lab, flows) -> bool:
    """Reset the lab and confirm every flow matches intent before spending anything."""
    try:
        lab.reset()
        res = evaluate(lab, flows)
    except Exception as e:  # Docker down, containers missing
        print(f"PREFLIGHT FAILED: {type(e).__name__}: {e}")
        return False
    if not is_healthy(res):
        print(format_table(res))
        print("PREFLIGHT FAILED: the lab is not healthy")
        return False
    return True


MAX_CONSECUTIVE_ERRORS = 3
FREEZE_TAG = "p3.0-freeze"


def needs_freeze(split: str, agent: str) -> bool:
    """Model runs on held-out or adversarial variants are only allowed after the prompt freeze."""
    return split in ("heldout", "adversarial") and agent != "baseline"


def freeze_tag_exists() -> bool:
    r = subprocess.run(["git", "rev-parse", "-q", "--verify", f"refs/tags/{FREEZE_TAG}"],
                       capture_output=True, text=True)
    return r.returncode == 0


def freeze_guard(split: str, agent: str, allow_unfrozen: bool) -> bool:
    if not needs_freeze(split, agent) or allow_unfrozen or freeze_tag_exists():
        return True
    print(f"REFUSED: model runs on the {split} split need the git tag {FREEZE_TAG} (Step 6).")
    print("Tag the frozen prompt first, or pass --allow-unfrozen if you really mean to spend a held-out run.")
    return False


def cmd_eval(args) -> int:
    topo, lab, flows = _lab()
    store = _store()
    if args.resume:
        cfg = store.get_eval(args.resume)
        if not cfg:
            print(f"no eval named {args.resume}")
            return 2
        eval_id = args.resume
        agent, profile, split, label = cfg["agent"], cfg["profile"], cfg["split"], cfg["label"]
        classes, seeds, repeats = cfg["faults"].split(","), _seeds(cfg["seeds"]), cfg["repeats"]
        cleanup = bool(cfg["cleanup"])
        print(f"resuming {eval_id}")
    else:
        agent, profile, split, label = args.agent, args.profile, args.split, args.label
        cleanup = not args.no_cleanup
        classes, seeds, repeats = _classes(args.faults, split), _seeds(args.seeds), args.repeats
        who = agent if agent in ("baseline", "router") else (profile or load_profiles().get("default", "env"))
        eval_id = f"eval-{time.strftime('%Y%m%d-%H%M%S')}-{who}" + (f"-{label}" if label else "")
        from .agent import PROMPT_VERSION

        store.register_eval(eval_id, label=label, split=split, agent=agent, profile=profile,
                            faults=",".join(classes), seeds=",".join(map(str, seeds)), repeats=repeats,
                            cleanup=int(cleanup), prompt_version=PROMPT_VERSION)
    if not freeze_guard(split, agent, args.allow_unfrozen):
        return 2
    jobs = pending_jobs(classes, seeds, repeats, store.done_keys(eval_id))
    print(f"{eval_id}: {len(jobs)} runs to do")
    if not args.no_preflight and not preflight(lab, flows):
        print(f"Fix the lab, then: np eval --resume {eval_id}")
        return 2
    records, consecutive_errors = [], 0
    for fault, seed, rep in jobs:
        try:
            rec = run_scenario(lab, topo, flows, fault, seed, agent, profile=profile, repeat=rep,
                               split=split, cleanup=cleanup)
        except Exception as e:
            rec = {"run_id": f"{eval_id}-{fault}-s{seed}-r{rep}-{int(time.time())}", "agent": agent,
                   "profile": profile, "repeat": rep, "split": split,
                   "scenario": {"fault_class": fault, "seed": seed, "split": split}, "outcome": "ERROR",
                   "error": f"{type(e).__name__}: {e}", "plan_count": 0, "gate_rejections": 0,
                   "collateral_rollbacks": 0, "cost_usd": 0.0, "wall_seconds": 0.0, "steps": 0}
        rec["label"] = label
        _finish(rec, store, eval_id=eval_id, subdir=eval_id)
        records.append(rec)
        print(f"{fault:<18} seed={seed:<3} rep={rep} -> {rec['outcome']:<24} "
              f"clean={rec.get('clean_fix')} ${rec.get('cost_usd', 0):.4f} {rec.get('wall_seconds', 0)}s")
        consecutive_errors = consecutive_errors + 1 if rec["outcome"] == "ERROR" else 0
        if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
            print(f"STOPPED after {consecutive_errors} errors in a row: {rec.get('error')}")
            print(f"Check `np doctor`, then: np eval --resume {eval_id}")
            return 3
    store.finish_eval(eval_id)
    rows = store.scoreboard([eval_id])
    (RUNS_DIR / eval_id).mkdir(parents=True, exist_ok=True)
    (RUNS_DIR / eval_id / "summary.json").write_text(json.dumps({"eval_id": eval_id, "rows": rows}, indent=2))
    print(json.dumps(rows, indent=2))
    return 0


def cmd_scoreboard(args) -> int:
    store = _store()
    if args.label:
        rows, what = store.scoreboard(label=args.label), f"label {args.label}"
    else:
        evals = args.eval or [e["eval_id"] for e in store.evals()]
        rows, what = store.scoreboard(evals), f"evals: {', '.join(evals) or '(none)'}"
    print(what + "\n")
    f = lambda v: "-" if v is None else v
    for r in rows:
        print(f"{r['agent']:<9} {r['profile']:<11} runs={r['runs']} errors={r['errors']} "
              f"fix={f(r['fix_rate'])} {f(r['fix_ci'])} clean={f(r['clean_fix_rate'])} {f(r['clean_ci'])} "
              f"diag={f(r['diagnosis_rate'])} consistent={f(r['consistent_variants'])}")
        print(f"    unsafe_attempts={r['unsafe_attempts']} (gate {r['gate_rejections']}, collateral "
              f"{r['collateral_rollbacks']}) took_bait={r['runs_taking_bait']} "
              f"policy_intact={f(r['policy_intact_rate'])} escalation={f(r['escalation_rate'])} "
              f"median ${f(r['median_cost_usd'])} total ${r['total_cost_usd']} median {f(r['median_seconds'])}s")
        print(f"    by class: {r['by_class']}")
    return 0


def cmd_doctor(_args) -> int:
    """Pre-flight for long sessions: Docker, containers, lab health, keys, database."""
    import os
    import shutil

    ok = True

    def line(good: bool, what: str, hint: str = "") -> None:
        nonlocal ok
        ok = ok and good
        print(f"[{'ok' if good else 'FAIL'}] {what}" + (f"  -> {hint}" if hint and not good else ""))

    line(shutil.which("docker") is not None, "docker CLI on PATH", "install or start Docker Desktop")
    info = subprocess.run(["docker", "info", "--format", "{{.ServerVersion}}"], capture_output=True, text=True)
    line(info.returncode == 0, f"Docker engine reachable ({info.stdout.strip() or 'no answer'})",
         "start Docker Desktop and wait for it to say running")
    ps = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True)
    names = set(ps.stdout.split())
    topo = load_topology()
    missing = [n for n in topo.nodes if f"np-{n}" not in names]
    line(not missing, f"lab containers running ({len(topo.nodes) - len(missing)}/{len(topo.nodes)})",
         "docker compose -f lab/docker-compose.yml up -d")
    if not missing:
        _, lab, flows = _lab()
        line(preflight(lab, flows), "lab provisions and every flow matches intent", "see the table above")
    for name, prof in load_profiles().get("profiles", {}).items():
        print(f"[{'ok' if os.environ.get(prof['key_env']) else '--'}] key for profile {name} ({prof['key_env']})")
    try:
        _store().list_runs(limit=1)
        line(True, f"run store {RUNS_DIR / 'netproof.db'}")
    except Exception as e:
        line(False, f"run store: {e}", "close any program holding runs/netproof.db")
    print("\nREADY" if ok else "\nNOT READY")
    return 0 if ok else 1


def cmd_report(args) -> int:
    from .report import write_report

    path = RUNS_DIR.glob(f"**/{args.run}.json")
    files = list(path)
    if not files:
        print(f"no record named {args.run}.json under runs/")
        return 1
    rec = json.loads(files[0].read_text())
    print(write_report(rec))
    return 0


def cmd_results(args) -> int:
    from .publish import results_markdown

    md = results_markdown(_store(), args.label, repeats=args.repeats)
    if args.out:
        from pathlib import Path

        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(md, encoding="utf-8", newline="\n")
        print(f"wrote {args.out}")
    else:
        print(md)
    return 0


def _featured(specs: List[str]) -> List[tuple]:
    out = []
    for spec in specs or []:
        if "=" not in spec:
            raise SystemExit(f"--featured needs RUN_ID=Title, got {spec!r}")
        rid, title = spec.split("=", 1)
        out.append((rid.strip(), title.strip()))
    return out


def cmd_export_site(args) -> int:
    import getpass
    from pathlib import Path

    from .config import ROOT
    from .publish import export_site, leaks

    info = export_site(_store(), Path(args.out), labels=args.label or [], replay_labels=args.replay_label or [],
                       featured=_featured(args.featured), repeats=args.repeats)
    print(f"exported {info['runs']} replayable runs, labels {info['labels']}, "
          f"{info['bytes'] / 1e6:.1f} MB -> {args.out}")
    found = leaks(Path(args.out), [str(ROOT), str(Path.home()), getpass.getuser()])
    if found:
        print("LOCAL DETAILS FOUND IN THE SITE (do not publish):")
        for f in found[:20]:
            print("  " + f)
        return 1
    return 0


def cmd_demo(args) -> int:
    from .demo import demo_run_id, run_seeded

    topo, lab, flows = _lab()
    store = _store()
    run_id = demo_run_id(args.kind, args.fault, args.seed, args.split)
    rec = run_seeded(lab, topo, flows, args.fault, args.seed, args.kind, split=args.split,
                     emit=store.emitter(run_id), run_id=run_id)
    _finish(rec, store)
    print(f"seeded {args.kind}: outcome={rec['outcome']} policy_intact={rec['policy_intact']} run={run_id}")
    if rec["plans"][0]["result"].get("gate_violations"):
        print("gate:", rec["plans"][0]["result"]["gate_violations"])
    if rec["plans"][0]["result"].get("regressions"):
        print("regressions:", rec["plans"][0]["result"]["regressions"],
              "restored:", rec["plans"][0]["result"].get("restored_ok"))
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
    classes = classes_for(args.split)
    for i in range(args.n):
        fault = classes[i % len(classes)]
        t = time.monotonic()
        lab.reset()
        times.append(time.monotonic() - t)
        try:
            prepare(lab, topo, flows, fault, i, args.split)
        except RuntimeError as e:
            failures += 1
            print(f"run {i} ({fault}): {e}")
    lab.reset()
    print(f"reset seconds: median={statistics.median(times):.1f} max={max(times):.1f}")
    print(f"post-injection checks passed: {args.n - failures}/{args.n}")
    return 0 if failures == 0 and max(times) <= 15 else 1


def cmd_validate_verifier(args) -> int:
    """Reference fixes commit, heal and leave zero residual; bad fixes roll back to identical state.
    Reference fixes run with the cleanup rule on, so a plan that only removes leftovers can commit."""
    from .executor import Executor, PlanOutcome
    from .minimality import residual, residual_count

    topo, lab, flows = _lab()
    fix_ok = fix_total = bad_ok = bad_total = 0
    for fault in _classes(args.faults, args.split):
        for idx, v in enumerate(SPLITS[args.split][fault]):
            # reference fixes, applied in order
            p = prepare(lab, topo, flows, fault, idx, args.split)
            golden = p.golden
            ex = Executor(lab, flows, drift_fn=lambda: residual(golden, {n: lab.snapshot(n) for n in topo.nodes}))
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
                p = prepare(lab, topo, flows, fault, idx, args.split)
                ex = Executor(lab, flows)
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
    splits = sorted(SPLITS)
    sub.add_parser("lab-up").set_defaults(fn=cmd_lab_up)
    sub.add_parser("lab-down").set_defaults(fn=cmd_lab_down)
    sub.add_parser("provision").set_defaults(fn=cmd_provision)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    sp = sub.add_parser("scenarios")
    sp.add_argument("--classes", default="all", help="all | phase1 | new | comma list")
    sp.add_argument("--split", default="dev", choices=splits)
    sp.set_defaults(fn=cmd_scenarios)
    for name, fn in (("inject", cmd_inject), ("run", cmd_run)):
        sp = sub.add_parser(name)
        sp.add_argument("--fault", required=True)
        sp.add_argument("--seed", type=int, default=0)
        sp.add_argument("--split", default="dev", choices=splits)
        if name == "run":
            sp.add_argument("--agent", choices=["llm", "baseline", "router"], default="llm")
            sp.add_argument("--profile", default=None, help="model profile from models.yaml")
            sp.add_argument("--no-cleanup", action="store_true", help="disable drift cleanup after a heal")
            sp.add_argument("--allow-unfrozen", action="store_true", help=argparse.SUPPRESS)
        sp.set_defaults(fn=fn)
    ev = sub.add_parser("eval")
    ev.add_argument("--agent", choices=["llm", "baseline", "router"], default="llm")
    ev.add_argument("--profile", default=None)
    ev.add_argument("--split", default="dev", choices=splits)
    ev.add_argument("--faults", default="all", help="all | phase1 | new | comma list")
    ev.add_argument("--seeds", default="0-2")
    ev.add_argument("--repeats", type=int, default=1)
    ev.add_argument("--label", default="")
    ev.add_argument("--no-cleanup", action="store_true")
    ev.add_argument("--resume", default=None, help="eval id to continue; other options are taken from it")
    ev.add_argument("--no-preflight", action="store_true")
    ev.add_argument("--allow-unfrozen", action="store_true", help=argparse.SUPPRESS)
    ev.set_defaults(fn=cmd_eval)
    sb = sub.add_parser("scoreboard")
    sb.add_argument("--eval", action="append", help="eval id; repeat for several; default all")
    sb.add_argument("--label", default=None, help="every eval registered under this label")
    sb.set_defaults(fn=cmd_scoreboard)
    rp = sub.add_parser("report")
    rp.add_argument("--run", required=True, help="run id (record file name without .json)")
    rp.set_defaults(fn=cmd_report)
    sv = sub.add_parser("serve")
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=8000)
    sv.set_defaults(fn=cmd_serve)
    rs = sub.add_parser("results")
    rs.add_argument("--label", action="append", required=True, help="label to tabulate; repeat for several")
    rs.add_argument("--out", default=None, help="write Markdown here (e.g. docs/results.md)")
    rs.add_argument("--repeats", type=int, default=None, help="count only the first N repeats of each variant")
    rs.set_defaults(fn=cmd_results)
    es = sub.add_parser("export-site")
    es.add_argument("--out", default="site")
    es.add_argument("--label", action="append", help="scoreboard to include; repeat")
    es.add_argument("--replay-label", action="append", help="label whose runs get full replays; repeat")
    es.add_argument("--featured", action="append", help="RUN_ID=Title shown as a button; repeat")
    es.add_argument("--repeats", type=int, default=None, help="count only the first N repeats of each variant")
    es.set_defaults(fn=cmd_export_site)
    dm = sub.add_parser("demo")
    dm.add_argument("--kind", choices=["bad_fix", "gate"], required=True)
    dm.add_argument("--fault", required=True)
    dm.add_argument("--seed", type=int, default=0)
    dm.add_argument("--split", default="dev", choices=splits)
    dm.set_defaults(fn=cmd_demo)
    vl = sub.add_parser("validate-lab")
    vl.add_argument("--n", type=int, default=27)
    vl.add_argument("--split", default="dev", choices=splits)
    vl.set_defaults(fn=cmd_validate_lab)
    vv = sub.add_parser("validate-verifier")
    vv.add_argument("--faults", default="all")
    vv.add_argument("--split", default="dev", choices=splits)
    vv.set_defaults(fn=cmd_validate_verifier)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
