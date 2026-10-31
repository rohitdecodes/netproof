"""SQLite run store: one row per run, the ordered event stream the dashboard replays,
and an eval registry so long evals can be resumed and grouped under a label."""
from __future__ import annotations

import json
import math
import sqlite3
import statistics
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import DB_PATH

RUN_COLUMNS = [
    ("run_id", "TEXT PRIMARY KEY"), ("created", "REAL"), ("eval_id", "TEXT"), ("agent", "TEXT"),
    ("profile", "TEXT"), ("model", "TEXT"), ("fault_class", "TEXT"), ("variant", "TEXT"), ("seed", "INTEGER"),
    ("repeat", "INTEGER"), ("outcome", "TEXT"), ("diagnosis_correct", "INTEGER"), ("clean_fix", "INTEGER"),
    ("residual_count", "INTEGER"), ("gate_rejections", "INTEGER"), ("collateral_rollbacks", "INTEGER"),
    ("plan_count", "INTEGER"), ("steps", "INTEGER"), ("cost_usd", "REAL"), ("wall_seconds", "REAL"),
    ("record_path", "TEXT"), ("report_path", "TEXT"),
    # Phase 3 columns (added to existing databases by _migrate)
    ("split", "TEXT"), ("label", "TEXT"), ("prompt_version", "TEXT"), ("unsafe_attempts", "INTEGER"),
    ("trap_hits", "INTEGER"), ("policy_intact", "INTEGER"), ("escalated", "INTEGER"),
    ("drift_at_heal", "INTEGER"), ("cleanup_enabled", "INTEGER"),
]

SCHEMA = f"""
CREATE TABLE IF NOT EXISTS runs ({", ".join(f"{n} {t}" for n, t in RUN_COLUMNS[:22])});
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT, seq INTEGER, ts REAL, type TEXT, data TEXT, PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS evals (
    eval_id TEXT PRIMARY KEY, label TEXT, split TEXT, agent TEXT, profile TEXT, faults TEXT, seeds TEXT,
    repeats INTEGER, cleanup INTEGER, prompt_version TEXT, started REAL, finished REAL
);
"""


def wilson(k: int, n: int, z: float = 1.96) -> Optional[Tuple[float, float]]:
    """95% Wilson score interval for k successes out of n."""
    if n == 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq: Dict[str, int] = {}
        with self._conn() as c:
            c.executescript(SCHEMA)
            self._migrate(c)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    @staticmethod
    def _migrate(c: sqlite3.Connection) -> None:
        have = {r["name"] for r in c.execute("PRAGMA table_info(runs)")}
        for name, typ in RUN_COLUMNS:
            if name not in have:
                c.execute(f"ALTER TABLE runs ADD COLUMN {name} {typ}")

    # ---- events -----------------------------------------------------------
    def add_event(self, run_id: str, type_: str, data: dict) -> int:
        with self._lock:
            if run_id not in self._seq:
                with self._conn() as c:
                    row = c.execute("SELECT MAX(seq) AS m FROM events WHERE run_id=?", (run_id,)).fetchone()
                self._seq[run_id] = row["m"] or 0
            seq = self._seq[run_id] + 1
            self._seq[run_id] = seq
            with self._conn() as c:
                c.execute("INSERT INTO events VALUES (?,?,?,?,?)",
                          (run_id, seq, time.time(), type_, json.dumps(data, default=str)))
        return seq

    def emitter(self, run_id: str):
        return lambda type_, data: self.add_event(run_id, type_, data)

    def events(self, run_id: str, after: int = 0) -> List[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT seq, ts, type, data FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                             (run_id, after)).fetchall()
        return [{"seq": r["seq"], "ts": r["ts"], "type": r["type"], "data": json.loads(r["data"])} for r in rows]

    # ---- evals ------------------------------------------------------------
    def register_eval(self, eval_id: str, **cfg) -> None:
        cols = ["label", "split", "agent", "profile", "faults", "seeds", "repeats", "cleanup", "prompt_version"]
        with self._lock, self._conn() as c:
            c.execute("INSERT OR IGNORE INTO evals (eval_id, started) VALUES (?, ?)", (eval_id, time.time()))
            c.execute(f"UPDATE evals SET {', '.join(f'{k}=?' for k in cols)} WHERE eval_id=?",
                      [cfg.get(k) for k in cols] + [eval_id])

    def finish_eval(self, eval_id: str) -> None:
        with self._lock, self._conn() as c:
            c.execute("UPDATE evals SET finished=? WHERE eval_id=?", (time.time(), eval_id))

    def get_eval(self, eval_id: str) -> Optional[dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM evals WHERE eval_id=?", (eval_id,)).fetchone()
        return dict(r) if r else None

    def done_keys(self, eval_id: str) -> Set[Tuple[str, int, int]]:
        """(fault_class, seed, repeat) already completed without ERROR in this eval."""
        with self._conn() as c:
            rows = c.execute("SELECT fault_class, seed, repeat FROM runs WHERE eval_id=? AND outcome != 'ERROR'",
                             (eval_id,)).fetchall()
        return {(r["fault_class"], r["seed"], r["repeat"]) for r in rows}

    def eval_ids_for_label(self, label: str) -> List[str]:
        with self._conn() as c:
            rows = c.execute("SELECT eval_id FROM evals WHERE label=? ORDER BY started", (label,)).fetchall()
        return [r["eval_id"] for r in rows]

    # ---- runs -------------------------------------------------------------
    def save_run(self, rec: dict, eval_id: Optional[str] = None, record_path: Optional[str] = None,
                 report_path: Optional[str] = None) -> None:
        sc = rec.get("scenario", {})
        values = {
            "run_id": rec["run_id"], "created": time.time(), "eval_id": eval_id, "agent": rec.get("agent"),
            "profile": rec.get("profile"), "model": rec.get("model"), "fault_class": sc.get("fault_class"),
            "variant": sc.get("variant"), "seed": sc.get("seed"), "repeat": rec.get("repeat", 0),
            "outcome": rec.get("outcome"), "diagnosis_correct": _b(rec.get("diagnosis_correct")),
            "clean_fix": _b(rec.get("clean_fix")), "residual_count": rec.get("residual_count"),
            "gate_rejections": rec.get("gate_rejections", 0), "collateral_rollbacks": rec.get("collateral_rollbacks", 0),
            "plan_count": rec.get("plan_count", 0), "steps": rec.get("steps", 0),
            "cost_usd": rec.get("cost_usd", 0.0), "wall_seconds": rec.get("wall_seconds", 0.0),
            "record_path": record_path, "report_path": report_path,
            "split": rec.get("split") or sc.get("split") or "dev", "label": rec.get("label"),
            "prompt_version": rec.get("prompt_version"), "unsafe_attempts": rec.get("unsafe_attempts"),
            "trap_hits": rec.get("trap_hits"), "policy_intact": _b(rec.get("policy_intact")),
            "escalated": _b(rec.get("escalated")), "drift_at_heal": rec.get("drift_at_heal"),
            "cleanup_enabled": _b(rec.get("cleanup_enabled")),
        }
        names = [n for n, _ in RUN_COLUMNS]
        with self._lock, self._conn() as c:
            c.execute(f"INSERT OR REPLACE INTO runs ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                      [values[n] for n in names])

    def list_runs(self, limit: int = 50, eval_id: Optional[str] = None, label: Optional[str] = None) -> List[dict]:
        q, args, where = "SELECT * FROM runs", [], []
        if eval_id:
            where.append("eval_id=?")
            args.append(eval_id)
        if label:
            where.append("label=?")
            args.append(label)
        if where:
            q += " WHERE " + " AND ".join(where)
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY created DESC LIMIT ?", args + [limit]).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def evals(self) -> List[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT r.eval_id AS eval_id, COUNT(*) AS runs, MIN(r.created) AS started, "
                             "e.label AS label, e.split AS split FROM runs r LEFT JOIN evals e "
                             "ON r.eval_id = e.eval_id WHERE r.eval_id IS NOT NULL "
                             "GROUP BY r.eval_id ORDER BY started DESC").fetchall()
        return [dict(r) for r in rows]

    def labels(self) -> List[str]:
        with self._conn() as c:
            rows = c.execute("SELECT DISTINCT label FROM evals WHERE label IS NOT NULL AND label != ''").fetchall()
        return sorted(r["label"] for r in rows)

    def scoreboard(self, eval_ids: Optional[List[str]] = None, label: Optional[str] = None) -> List[dict]:
        if label:
            rows = self.list_runs(limit=1_000_000, label=label)
        else:
            rows = []
            for e in (eval_ids or [None]):
                rows += self.list_runs(limit=1_000_000, eval_id=e)
        return scoreboard(rows)


def pending_jobs(classes: List[str], seeds: List[int], repeats: int, done) -> List[tuple]:
    """Every (class, seed, repeat) in an eval that has not completed without ERROR.
    Repeat-major order: the whole set once, then again, so stopping at a repeat boundary
    leaves complete repeats behind."""
    return [(c, s, r) for r in range(repeats) for c in classes for s in seeds if (c, s, r) not in done]


def _b(v) -> Optional[int]:
    return None if v is None else int(bool(v))


def _rate(k: int, n: int) -> Optional[float]:
    return round(k / n, 3) if n else None


def scoreboard(rows: List[dict]) -> List[dict]:
    """One line per (agent, profile). Rates are over scored runs (ERROR runs excluded, but counted),
    with 95% Wilson intervals, per-class counts, and safety metrics."""
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["agent"], r["profile"] or "-")].append(r)
    out = []
    for (agent, profile), rs in sorted(groups.items()):
        scored = [r for r in rs if r["outcome"] != "ERROR"]
        n = len(scored)
        fixed = sum(r["outcome"] == "FIXED_VERIFIED" for r in scored)
        clean = sum(bool(r["clean_fix"]) for r in scored)
        by_class: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        by_variant: Dict[str, List[bool]] = defaultdict(list)
        for r in scored:
            by_class[r["fault_class"]][1] += 1
            by_class[r["fault_class"]][0] += r["outcome"] == "FIXED_VERIFIED"
            by_variant[r["variant"]].append(r["outcome"] == "FIXED_VERIFIED")
        repeated = [v for v in by_variant.values() if len(v) > 1]
        costs = [r["cost_usd"] or 0 for r in scored]
        intact = [r for r in scored if r.get("policy_intact") is not None]
        esc = [r for r in scored if r.get("escalated") is not None]
        out.append({
            "agent": agent, "profile": profile, "runs": len(rs), "errors": len(rs) - n,
            "n": n, "fixed": fixed, "clean": clean,
            "diagnosis_correct": sum(bool(r["diagnosis_correct"]) for r in scored),
            "policy_intact": sum(bool(r["policy_intact"]) for r in intact), "policy_intact_n": len(intact),
            "escalated": sum(bool(r["escalated"]) for r in esc), "escalated_n": len(esc),
            "cost_per_fix_usd": round(sum(costs) / fixed, 4) if fixed else None,
            "fix_rate": _rate(fixed, n), "fix_ci": wilson(fixed, n),
            "clean_fix_rate": _rate(clean, n), "clean_ci": wilson(clean, n),
            "diagnosis_rate": (_rate(sum(bool(r["diagnosis_correct"]) for r in scored), n)
                               if agent != "baseline" else None),
            "consistent_variants": (f"{sum(all(v) or not any(v) for v in repeated)}/{len(repeated)}"
                                    if repeated else None),
            "collateral_rollbacks": sum(r["collateral_rollbacks"] or 0 for r in scored),
            "gate_rejections": sum(r["gate_rejections"] or 0 for r in scored),
            "unsafe_attempts": sum(r.get("unsafe_attempts") or 0 for r in scored),
            "runs_taking_bait": sum(1 for r in scored if (r.get("trap_hits") or 0) > 0),
            "policy_intact_rate": _rate(sum(bool(r["policy_intact"]) for r in intact), len(intact)),
            "escalation_rate": _rate(sum(bool(r["escalated"]) for r in esc), len(esc)),
            "median_cost_usd": round(statistics.median(costs), 4) if costs else None,
            "total_cost_usd": round(sum(costs), 4),
            "median_seconds": (round(statistics.median([r["wall_seconds"] or 0 for r in scored]), 1)
                               if scored else None),
            "by_class": {c: f"{a}/{b}" for c, (a, b) in sorted(by_class.items())},
        })
    return out
