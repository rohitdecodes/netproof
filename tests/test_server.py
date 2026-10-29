import threading
import time

from fastapi.testclient import TestClient

from netproof.server import create_app
from netproof.store import Store

RELEASE = threading.Event()


def fake_run(run_id, req, emit):
    emit("run_started", {"run_id": run_id, "ticket": "t", "reported_flow": "staff_file_smb"})
    RELEASE.wait(5)
    rec = {"run_id": run_id, "agent": req.agent, "profile": req.profile, "model": "m",
           "scenario": {"fault_class": req.fault_class, "variant": req.fault_class + ".a", "seed": req.seed,
                        "ticket": "t"},
           "outcome": "FIXED_VERIFIED", "clean_fix": True, "diagnosis_correct": True, "residual_count": 0,
           "gate_rejections": 0, "collateral_rollbacks": 0, "plan_count": 1, "steps": 2, "plans": [],
           "cost_usd": 0.01, "wall_seconds": 1.0, "usage": {}}
    emit("run_finished", {"outcome": "FIXED_VERIFIED"})
    return rec


def client(tmp_path):
    app = create_app(run_fn=fake_run, store=Store(tmp_path / "s.db"), check_fn=lambda: {"staff_file_smb": True},
                     runs_dir=tmp_path / "runs", reports_dir=tmp_path / "reports")
    return TestClient(app)


def wait_for(c, run_id, event_type, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        if any(e["type"] == event_type for e in c.get(f"/api/runs/{run_id}/events").json()):
            return True
        time.sleep(0.05)
    return False


def test_run_lifecycle(tmp_path):
    RELEASE.clear()
    c = client(tmp_path)
    r = c.post("/api/runs", json={"fault_class": "route_missing", "seed": 0, "agent": "baseline"})
    assert r.status_code == 200
    run_id = r.json()["run_id"]
    assert c.get("/api/status").json()["active"] == run_id
    busy = c.post("/api/runs", json={"fault_class": "route_missing", "seed": 1, "agent": "baseline"})
    assert busy.status_code == 409
    assert c.get("/api/lab/check").status_code == 409
    RELEASE.set()
    assert wait_for(c, run_id, "saved")
    assert c.get("/api/status").json()["active"] is None
    assert c.get("/api/runs").json()[0]["run_id"] == run_id
    assert c.get(f"/api/runs/{run_id}/report").text.startswith("# Incident report")
    assert c.get("/api/lab/check").json() == {"staff_file_smb": True}


def test_input_validation(tmp_path):
    c = client(tmp_path)
    assert c.post("/api/runs", json={"fault_class": "nope"}).status_code == 422
    assert c.post("/api/runs", json={"fault_class": "route_missing", "agent": "x"}).status_code == 422
    assert c.post("/api/runs", json={"fault_class": "route_missing", "profile": "nope"}).status_code == 422
    assert c.get("/api/runs/does-not-exist").status_code == 404


def test_static_pages_and_metadata(tmp_path):
    c = client(tmp_path)
    assert c.get("/").status_code == 200 and "NetProof" in c.get("/").text
    assert c.get("/static/app.js").status_code == 200
    topo = c.get("/api/topology").json()
    assert len(topo["nodes"]) == 6 and len(topo["flows"]) == 13
    assert len(c.get("/api/catalog").json()) == 9
    names = [p["name"] for p in c.get("/api/profiles").json()["profiles"]]
    assert "spark-1.3" in names and "spark-open" in names
