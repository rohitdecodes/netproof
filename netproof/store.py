"""SQLite run store: one row per run, plus the ordered event stream the dashboard replays."""
from __future__ import annotations

import json
import sqlite3
import statistics
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional

from .config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY, created REAL, eval_id TEXT, agent TEXT, profile TEXT, model TEXT,
    fault_class TEXT, variant TEXT, seed INTEGER, repeat INTEGER, outcome TEXT,
    diagnosis_correct INTEGER, clean_fix INTEGER, residual_count INTEGER,
    gate_rejections INTEGER, collateral_rollbacks INTEGER, plan_count INTEGER, steps INTEGER,
    cost_usd REAL, wall_seconds REAL, record_path TEXT, report_path TEXT
);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT, seq INTEGER, ts REAL, type TEXT, data TEXT, PRIMARY KEY (run_id, seq)
);
"""


class Store:
    def __init__(self, path: Optional[Path] = None):
        self.path = Path(path or DB_PATH)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._seq: Dict[str, int] = {}
        with self._conn() as c:
            c.executescript(SCHEMA)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=10)
        conn.row_factory = sqlite3.Row
        return conn

    # ---- events -----------------------------------------------------------
    def add_event(self, run_id: str, type_: str, data: dict) -> int:
        with self._lock:
            seq = self._seq.get(run_id, 0) + 1
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

    # ---- runs -------------------------------------------------------------
    def save_run(self, rec: dict, eval_id: Optional[str] = None, record_path: Optional[str] = None,
                 report_path: Optional[str] = None) -> None:
        sc = rec.get("scenario", {})
        row = (rec["run_id"], time.time(), eval_id, rec.get("agent"), rec.get("profile"), rec.get("model"),
               sc.get("fault_class"), sc.get("variant"), sc.get("seed"), rec.get("repeat", 0),
               rec.get("outcome"), _b(rec.get("diagnosis_correct")), _b(rec.get("clean_fix")),
               rec.get("residual_count"), rec.get("gate_rejections", 0), rec.get("collateral_rollbacks", 0),
               rec.get("plan_count", 0), rec.get("steps", 0), rec.get("cost_usd", 0.0),
               rec.get("wall_seconds", 0.0), record_path, report_path)
        with self._lock, self._conn() as c:
            c.execute("INSERT OR REPLACE INTO runs VALUES (" + ",".join("?" * len(row)) + ")", row)

    def list_runs(self, limit: int = 50, eval_id: Optional[str] = None) -> List[dict]:
        q, args = "SELECT * FROM runs", []
        if eval_id:
            q, args = q + " WHERE eval_id=?", [eval_id]
        with self._conn() as c:
            rows = c.execute(q + " ORDER BY created DESC LIMIT ?", args + [limit]).fetchall()
        return [dict(r) for r in rows]

    def get_run(self, run_id: str) -> Optional[dict]:
        with self._conn() as c:
            r = c.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        return dict(r) if r else None

    def evals(self) -> List[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT eval_id, COUNT(*) AS runs, MIN(created) AS started FROM runs "
                             "WHERE eval_id IS NOT NULL GROUP BY eval_id ORDER BY started DESC").fetchall()
        return [dict(r) for r in rows]

    def scoreboard(self, eval_ids: Optional[List[str]] = None) -> List[dict]:
        rows = []
        for e in (eval_ids or [None]):
            rows += self.list_runs(limit=100000, eval_id=e)
        return scoreboard(rows)


def _b(v) -> Optional[int]:
    return None if v is None else int(bool(v))


def scoreboard(rows: List[dict]) -> List[dict]:
    """One line per (agent, profile): rates over scored runs (ERROR runs excluded, but counted)."""
    groups: Dict[tuple, List[dict]] = defaultdict(list)
    for r in rows:
        groups[(r["agent"], r["profile"] or "-")].append(r)
    out = []
    for (agent, profile), rs in sorted(groups.items()):
        scored = [r for r in rs if r["outcome"] != "ERROR"]
        n = len(scored)
        fixed = [r for r in scored if r["outcome"] == "FIXED_VERIFIED"]
        by_class: Dict[str, List[int]] = defaultdict(lambda: [0, 0])
        for r in scored:
            by_class[r["fault_class"]][1] += 1
            by_class[r["fault_class"]][0] += r["outcome"] == "FIXED_VERIFIED"
        costs = [r["cost_usd"] or 0 for r in scored]
        out.append({
            "agent": agent, "profile": profile, "runs": len(rs), "errors": len(rs) - n,
            "fix_rate": round(len(fixed) / n, 3) if n else None,
            "clean_fix_rate": round(sum(bool(r["clean_fix"]) for r in scored) / n, 3) if n else None,
            "diagnosis_rate": (round(sum(bool(r["diagnosis_correct"]) for r in scored) / n, 3)
                               if n and agent != "baseline" else None),
            "collateral_rollbacks": sum(r["collateral_rollbacks"] or 0 for r in scored),
            "gate_rejections": sum(r["gate_rejections"] or 0 for r in scored),
            "median_cost_usd": round(statistics.median(costs), 4) if costs else None,
            "total_cost_usd": round(sum(costs), 4),
            "median_seconds": statistics.median([r["wall_seconds"] or 0 for r in scored]) if scored else None,
            "by_class": {c: f"{a}/{b}" for c, (a, b) in sorted(by_class.items())},
        })
    return out
