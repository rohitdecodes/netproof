from netproof.store import Store, scoreboard


def rec(run_id, outcome, clean, agent="llm", profile="spark-1.3", fault="route_missing", cost=0.02):
    return {"run_id": run_id, "agent": agent, "profile": profile, "model": "m",
            "scenario": {"fault_class": fault, "variant": fault + ".a", "seed": 0}, "outcome": outcome,
            "diagnosis_correct": True, "clean_fix": clean, "residual_count": 0 if clean else 2,
            "gate_rejections": 0, "collateral_rollbacks": 1, "plan_count": 1, "steps": 3,
            "cost_usd": cost, "wall_seconds": 30.0}


def test_events_are_ordered_and_resumable(tmp_path):
    st = Store(tmp_path / "t.db")
    emit = st.emitter("r1")
    emit("a", {"x": 1})
    emit("b", {"x": 2})
    emit("c", {"x": 3})
    assert [e["type"] for e in st.events("r1")] == ["a", "b", "c"]
    assert [e["type"] for e in st.events("r1", after=2)] == ["c"]


def test_runs_and_scoreboard(tmp_path):
    st = Store(tmp_path / "t.db")
    st.save_run(rec("r1", "FIXED_VERIFIED", True), eval_id="e1")
    st.save_run(rec("r2", "FIXED_VERIFIED", False, fault="acl_typo"), eval_id="e1")
    st.save_run(rec("r3", "ROLLED_BACK_NO_EFFECT", False, agent="baseline", profile=None), eval_id="e1")
    st.save_run(rec("r4", "ERROR", False), eval_id="e1")
    assert [e["eval_id"] for e in st.evals()] == ["e1"]
    rows = {(r["agent"], r["profile"]): r for r in st.scoreboard(["e1"])}
    llm = rows[("llm", "spark-1.3")]
    assert llm["runs"] == 3 and llm["errors"] == 1 and llm["fix_rate"] == 1.0 and llm["clean_fix_rate"] == 0.5
    assert llm["by_class"] == {"acl_typo": "1/1", "route_missing": "1/1"}
    assert rows[("baseline", "-")]["fix_rate"] == 0.0 and rows[("baseline", "-")]["diagnosis_rate"] is None


def test_scoreboard_handles_empty_input():
    assert scoreboard([]) == []
