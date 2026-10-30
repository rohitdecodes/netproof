"""Dashboard API. Start with:  python -m netproof.cli serve   then open http://127.0.0.1:8000

One run at a time (there is one lab). The browser polls /api/runs/{id}/events for live updates;
the same endpoint replays any finished run.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import ROOT, load_profiles
from .faults import SPLITS
from .intent import load_intent
from .records import write_record
from .report import write_report
from .runner import new_run_id, run_scenario
from .store import Store
from .topology import load_topology

WEB_DIR = ROOT / "web"


class RunRequest(BaseModel):
    fault_class: str
    seed: int = 0
    agent: str = "llm"
    profile: Optional[str] = None
    split: str = "dev"


def default_run_fn(run_id: str, req: RunRequest, emit: Callable[[str, dict], None]) -> dict:
    from .lab import DockerLab

    topo = load_topology()
    return run_scenario(DockerLab(topo), topo, load_intent(), req.fault_class, req.seed, req.agent,
                        profile=req.profile, emit=emit, run_id=run_id, split=req.split)


def default_check_fn() -> dict:
    from .intent import evaluate
    from .lab import DockerLab

    return {fid: r.ok for fid, r in evaluate(DockerLab(load_topology()), load_intent()).items()}


def create_app(run_fn: Optional[Callable] = None, store: Optional[Store] = None,
               check_fn: Optional[Callable] = None, runs_dir: Optional[Path] = None,
               reports_dir: Optional[Path] = None) -> FastAPI:
    app = FastAPI(title="NetProof")
    store = store or Store()
    run_fn = run_fn or default_run_fn
    check_fn = check_fn or default_check_fn
    lock = threading.Lock()
    state = {"active": None}
    topo = load_topology()
    flows = load_intent()

    def worker(run_id: str, req: RunRequest) -> None:
        emit = store.emitter(run_id)
        try:
            rec = run_fn(run_id, req, emit)
            rec["run_id"] = run_id
            path = write_record(rec, base=runs_dir)
            report = write_report(rec, folder=reports_dir)
            store.save_run(rec, record_path=str(path), report_path=str(report))
            emit("saved", {"report": str(report)})
        except Exception as e:
            emit("run_failed", {"error": f"{type(e).__name__}: {e}"})
        finally:
            with lock:
                state["active"] = None

    @app.get("/api/status")
    def status():
        return {"active": state["active"]}

    @app.get("/api/topology")
    def topology():
        return {
            "nodes": [{"name": n, "role": node.role, "interfaces": node.interfaces}
                      for n, node in topo.nodes.items()],
            "networks": {k: {"subnet": v["subnet"]} for k, v in topo.networks.items()},
            "flows": [f.__dict__ for f in flows],
        }

    @app.get("/api/catalog")
    def catalog(split: str = "dev"):
        if split not in SPLITS:
            raise HTTPException(422, f"unknown split {split!r}")
        return {c: [{"seed": i, "variant": v.key, "reported_flow": v.reported_flow}
                    for i, v in enumerate(vs)] for c, vs in SPLITS[split].items()}

    @app.get("/api/profiles")
    def profiles():
        import os

        data = load_profiles()
        return {"default": data.get("default"),
                "profiles": [{"name": k, "model": v["model"], "key_present": bool(os.environ.get(v["key_env"]))}
                             for k, v in data.get("profiles", {}).items()]}

    @app.post("/api/runs")
    def start_run(req: RunRequest):
        if req.split not in SPLITS:
            raise HTTPException(422, f"unknown split {req.split!r}")
        if req.fault_class not in SPLITS[req.split]:
            raise HTTPException(422, f"unknown fault class {req.fault_class!r} in split {req.split}")
        if req.agent not in ("llm", "baseline", "router"):
            raise HTTPException(422, "agent must be llm, baseline or router")
        profiles_known = load_profiles().get("profiles", {})
        if req.agent == "llm" and req.profile and req.profile not in profiles_known:
            raise HTTPException(422, f"unknown profile {req.profile!r}")
        with lock:
            if state["active"]:
                raise HTTPException(409, f"run {state['active']} is still in progress")
            profile = req.profile or load_profiles().get("default")
            sid = f"{req.fault_class}-s{req.seed}" if req.split == "dev" else f"{req.split}-{req.fault_class}-s{req.seed}"
            run_id = new_run_id(req.agent, sid, 0, profile)
            state["active"] = run_id
        threading.Thread(target=worker, args=(run_id, req), daemon=True).start()
        return {"run_id": run_id}

    @app.get("/api/runs")
    def runs(limit: int = 30):
        return store.list_runs(limit=limit)

    @app.get("/api/runs/{run_id}")
    def run(run_id: str):
        row = store.get_run(run_id)
        if row is None and state["active"] != run_id:
            raise HTTPException(404, "no such run")
        return {"run": row, "active": state["active"] == run_id}

    @app.get("/api/runs/{run_id}/events")
    def events(run_id: str, after: int = 0):
        return store.events(run_id, after)

    @app.get("/api/runs/{run_id}/report", response_class=PlainTextResponse)
    def report(run_id: str):
        row = store.get_run(run_id)
        if not row or not row.get("report_path") or not Path(row["report_path"]).exists():
            raise HTTPException(404, "no report for this run")
        return Path(row["report_path"]).read_text(encoding="utf-8")

    @app.get("/api/evals")
    def evals():
        return store.evals()

    @app.get("/api/labels")
    def labels():
        return store.labels()

    @app.get("/api/scoreboard")
    def scoreboard(eval: Optional[List[str]] = Query(default=None), label: Optional[str] = None):
        if label:
            return {"label": label, "evals": store.eval_ids_for_label(label), "rows": store.scoreboard(label=label)}
        ids = eval or [e["eval_id"] for e in store.evals()]
        return {"evals": ids, "rows": store.scoreboard(ids)}

    @app.get("/api/lab/check")
    def lab_check():
        if state["active"]:
            raise HTTPException(409, "a run is in progress")
        return check_fn()

    if WEB_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")

        @app.get("/")
        def index():
            return FileResponse(str(WEB_DIR / "index.html"))

    return app
