"""Incident report: a deterministic Markdown evidence file for one run. No model is involved."""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .config import REPORTS_DIR


def _flows_table(before: dict, after: dict) -> str:
    lines = ["| Flow | Before | After |", "| --- | --- | --- |"]
    for fid in before or after:
        b = "ok" if before.get(fid) else "FAIL"
        a = "ok" if after.get(fid) else "FAIL"
        lines.append(f"| {fid} | {b} | {a} |")
    return "\n".join(lines)


def render_report(rec: dict) -> str:
    sc = rec.get("scenario", {})
    gt = rec.get("ground_truth") or sc.get("ground_truth") or []
    who = "scripted baseline" if rec.get("agent") == "baseline" else f"{rec.get('profile')} ({rec.get('model')})"
    out = [
        f"# Incident report: {rec.get('run_id')}",
        "",
        f"**Outcome:** {rec.get('outcome')}  ",
        f"**Clean fix:** {'yes' if rec.get('clean_fix') else 'no'}  ",
        f"**Agent:** {who}  ",
        f"**Scenario:** {sc.get('scenario_id')} (variant {sc.get('variant')})",
        "",
        "## Ticket",
        "",
        f"> {sc.get('ticket', '')}",
        "",
        "## Ground truth (revealed after the run)",
        "",
    ]
    out += [f"- {g['device']}: {g['fault_class']}" for g in gt] or ["- (not recorded)"]
    rcs = rec.get("root_causes") or ([rec["root_cause"]] if rec.get("root_cause") else [])
    out += ["", "## Agent's diagnosis", ""]
    if rcs:
        out += [f"- {rc.get('device')}: {rc.get('fault_class')} ({rc.get('summary', '')})" for rc in rcs]
        out += ["", f"Diagnosis correct: {'yes' if rec.get('diagnosis_correct') else 'no'}"]
    else:
        out += ["- none submitted"]

    out += ["", "## Changes attempted", ""]
    for p in rec.get("plans", []):
        r = p["result"]
        out += [f"### Plan {p['index'] + 1} on {p['plan']['device']}: {r['outcome']}", ""]
        out += ["```"] + p["plan"]["commands"] + ["```", ""]
        if r.get("gate_violations"):
            out += ["Gate violations:", ""] + [f"- {v}" for v in r["gate_violations"]] + [""]
        if r.get("apply_errors"):
            out += ["Command errors:", ""] + [f"- {v}" for v in r["apply_errors"]] + [""]
        if r.get("regressions"):
            out += [f"Regressions (caused the rollback): {', '.join(r['regressions'])}", ""]
        if r.get("improvements"):
            out += [f"Improved: {', '.join(r['improvements'])}", ""]
        if r.get("restored_ok") is not None:
            out += [f"Device restored to its previous state: {'yes' if r['restored_ok'] else 'NO'}", ""]
    if not rec.get("plans"):
        out += ["No plan was submitted.", ""]

    out += ["## Verification", "", _flows_table(rec.get("flows_before", {}), rec.get("final_flow_ok", {})), ""]

    res = rec.get("residual_items") or {}
    out += ["## Residual differences from the intended configuration", ""]
    if res:
        for node, items in res.items():
            out += [f"- **{node}**"] + [f"  - {i}" for i in items]
    else:
        out += ["None. The network matches its intended configuration."]

    hyps = rec.get("hypotheses") or []
    if hyps:
        out += ["", "## Hypotheses recorded", ""]
        out += [f"- [{h.get('status')}] {h.get('hypothesis')}" for h in hyps]

    calls = rec.get("tool_calls") or []
    if calls:
        out += ["", "## Investigation timeline", "", "| Step | Tool | Arguments |", "| --- | --- | --- |"]
        for c in calls:
            args = ", ".join(f"{k}={v}" for k, v in (c.get("args") or {}).items() if k != "plan")
            out.append(f"| {c.get('step')} | {c.get('tool')} | {args[:120]} |")

    out += ["", "## Cost and time", "",
            f"- Model calls: {rec.get('steps')}",
            f"- Tokens: {rec.get('usage', {})}",
            f"- Cost: ${rec.get('cost_usd', 0):.4f}",
            f"- Wall time: {rec.get('wall_seconds')} s"]
    if rec.get("error"):
        out += ["", f"**Error:** {rec['error']}"]
    return "\n".join(out) + "\n"


def write_report(rec: dict, folder: Optional[Path] = None) -> Path:
    folder = Path(folder or REPORTS_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{rec['run_id']}.md"
    path.write_text(render_report(rec), encoding="utf-8")
    return path
