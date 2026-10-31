import sqlite3

from netproof.store import Store, pending_jobs, wilson


def rec(run_id, outcome, variant="acl_typo.h1", profile="spark-1.3", seed=0, repeat=0, **extra):
    base = {"run_id": run_id, "agent": "llm", "profile": profile, "model": "m",
            "scenario": {"fault_class": variant.split(".")[0], "variant": variant, "seed": seed, "split": "heldout"},
            "outcome": outcome, "repeat": repeat, "diagnosis_correct": True, "clean_fix": outcome == "FIXED_VERIFIED",
            "residual_count": 0, "gate_rejections": 0, "collateral_rollbacks": 0, "plan_count": 1, "steps": 3,
            "cost_usd": 0.02, "wall_seconds": 30.0, "label": "heldout-v1", "unsafe_attempts": 0, "trap_hits": 0,
            "policy_intact": True, "escalated": None}
    base.update(extra)
    return base


def test_wilson_interval():
    assert wilson(0, 0) is None
    lo, hi = wilson(27, 27)
    assert hi == 1.0 and 0.87 < lo < 0.88
    lo, hi = wilson(5, 10)
    assert lo < 0.5 < hi


def test_old_phase2_database_is_migrated(tmp_path):
    db = tmp_path / "old.db"
    c = sqlite3.connect(db)
    c.execute("CREATE TABLE runs (run_id TEXT PRIMARY KEY, created REAL, eval_id TEXT, agent TEXT, profile TEXT, "
              "model TEXT, fault_class TEXT, variant TEXT, seed INTEGER, repeat INTEGER, outcome TEXT, "
              "diagnosis_correct INTEGER, clean_fix INTEGER, residual_count INTEGER, gate_rejections INTEGER, "
              "collateral_rollbacks INTEGER, plan_count INTEGER, steps INTEGER, cost_usd REAL, wall_seconds REAL, "
              "record_path TEXT, report_path TEXT)")
    c.execute("INSERT INTO runs (run_id, agent, outcome) VALUES ('old', 'llm', 'FIXED_VERIFIED')")
    c.commit()
    c.close()
    st = Store(db)
    assert st.get_run("old")["outcome"] == "FIXED_VERIFIED"
    st.save_run(rec("new", "FIXED_VERIFIED"))
    assert st.get_run("new")["label"] == "heldout-v1" and st.get_run("new")["split"] == "heldout"


def test_eval_registry_and_resume_keys(tmp_path):
    st = Store(tmp_path / "t.db")
    st.register_eval("e1", label="heldout-v1", split="heldout", agent="llm", profile="spark-1.3",
                     faults="acl_typo", seeds="0,1", repeats=2, cleanup=1, prompt_version="p3.0")
    st.save_run(rec("a", "FIXED_VERIFIED", seed=0, repeat=0), eval_id="e1")
    st.save_run(rec("b", "ERROR", seed=0, repeat=1), eval_id="e1")
    assert st.get_eval("e1")["repeats"] == 2
    done = st.done_keys("e1")
    assert done == {("acl_typo", 0, 0)}
    todo = pending_jobs(["acl_typo"], [0, 1], 2, done)
    assert todo == [("acl_typo", 1, 0), ("acl_typo", 0, 1), ("acl_typo", 1, 1)]   # repeat-major
    assert st.eval_ids_for_label("heldout-v1") == ["e1"] and st.labels() == ["heldout-v1"]


def test_label_scoreboard_with_intervals_consistency_and_safety(tmp_path):
    st = Store(tmp_path / "t.db")
    for i, out in enumerate(["FIXED_VERIFIED", "FIXED_VERIFIED", "ROLLED_BACK_NO_EFFECT"]):
        st.save_run(rec(f"x{i}", out, repeat=i, unsafe_attempts=1 if i == 2 else 0, trap_hits=1 if i == 2 else 0))
    st.save_run(rec("y0", "FIXED_VERIFIED", variant="acl_typo.h2", repeat=0))
    st.save_run(rec("y1", "FIXED_VERIFIED", variant="acl_typo.h2", repeat=1))
    row = st.scoreboard(label="heldout-v1")[0]
    assert row["runs"] == 5 and row["fix_rate"] == 0.8 and row["fix_ci"][0] < 0.8 < row["fix_ci"][1]
    assert row["consistent_variants"] == "1/2"
    assert row["unsafe_attempts"] == 1 and row["runs_taking_bait"] == 1 and row["policy_intact_rate"] == 1.0
