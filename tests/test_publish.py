"""Result tables and the static replay site."""
import json
import shutil
import subprocess
import textwrap

import pytest

from netproof.publish import export_site, leaks, results_markdown, _transform_app, _transform_index
from netproof.store import Store


def rec(run_id, outcome, label, agent="llm", profile="spark-1.3", fault="acl_typo", variant="acl_typo.h1",
        repeat=0, **extra):
    base = {"run_id": run_id, "agent": agent, "profile": profile, "model": "m", "label": label,
            "scenario": {"fault_class": fault, "variant": variant, "seed": 0, "split": "heldout"},
            "split": "heldout", "outcome": outcome, "repeat": repeat, "diagnosis_correct": True,
            "clean_fix": outcome == "FIXED_VERIFIED", "residual_count": 0, "gate_rejections": 0,
            "collateral_rollbacks": 0, "plan_count": 1, "steps": 3, "cost_usd": 0.03, "wall_seconds": 40.0,
            "unsafe_attempts": 0, "trap_hits": 0, "policy_intact": True, "escalated": None, "drift_at_heal": 0,
            "prompt_version": "p3.0"}
    base.update(extra)
    return base


@pytest.fixture
def store(tmp_path):
    st = Store(tmp_path / "t.db")
    report = tmp_path / "r1.md"
    report.write_text("# Incident report: r1\n\nfixed <ok>\n", encoding="utf-8")
    st.save_run(rec("r1", "FIXED_VERIFIED", "heldout-v1"), report_path=str(report), record_path="C:/secret/r1.json")
    st.save_run(rec("r2", "FIXED_VERIFIED", "heldout-v1", repeat=1, drift_at_heal=1, clean_fix=True))
    st.save_run(rec("r3", "ROLLED_BACK_NO_EFFECT", "heldout-v1", repeat=2, cost_usd=0.05))
    st.save_run(rec("b1", "FIXED_VERIFIED", "heldout-v1", agent="baseline", profile=None, cost_usd=0.0))
    st.save_run(rec("a1", "FIXED_VERIFIED", "adversarial-v1", fault="output_injection",
                    variant="output_injection.c", gate_rejections=1, unsafe_attempts=1, trap_hits=1))
    for rid in ("r1", "a1"):
        emit = st.emitter(rid)
        emit("run_started", {"run_id": rid, "ticket": "t"})
        emit("plan_submitted", {"index": 0})
        emit("run_finished", {"outcome": "FIXED_VERIFIED"})
        emit("saved", {"report": "C:/Users/someone/netproof/reports/x.md"})
    return st


def test_results_markdown_counts_intervals_and_safety(store):
    md = results_markdown(store, ["heldout-v1", "adversarial-v1", "empty-label"])
    assert "## heldout-v1" in md and "## adversarial-v1" in md and "No runs recorded under this label." in md
    assert "| spark-1.3 | 3 (0) | 2/3 (0.67;" in md          # fixed with rate and interval
    assert "| Scripted baseline | 1 (0) | 1/1 (1.00;" in md
    assert "| 1/2 |" in md                                   # clean at heal: r1 yes, r2 needed cleanup
    assert "$0.0550" in md                                   # cost per verified fix: 0.11 / 2
    assert "| spark-1.3 | 1 | 0 | 1/1 | 1/1 | - |" in md      # adversarial safety row
    assert "Prompt versions: p3.0." in md
    first = results_markdown(store, ["heldout-v1"], repeats=1)
    assert "| spark-1.3 | 1 (0) | 1/1 (1.00;" in first and "first 1 repeat(s)" in first
    per_label = results_markdown(store, ["heldout-v1", "adversarial-v1"], repeats={"heldout-v1": 1})
    assert "| spark-1.3 | 1 (0) | 1/1 (1.00;" in per_label           # held-out cut to repeat 0
    assert per_label.count("Only the first 1 repeat(s)") == 1         # stated once, under heldout-v1


def test_export_site_writes_a_replayable_site_without_local_paths(store, tmp_path):
    out = tmp_path / "site"
    info = export_site(store, out, labels=["heldout-v1", "adversarial-v1"], replay_labels=["adversarial-v1"],
                       featured=[("r1", "Model declines a planted instruction")])
    assert info["runs"] == 2
    runs = json.loads((out / "data" / "runs.json").read_text())
    assert [r["run_id"] for r in runs] == ["r1", "a1"] and runs[0]["featured_title"].startswith("Model declines")
    assert all("record_path" not in r and "report_path" not in r for r in runs)
    events = json.loads((out / "data" / "events" / "r1.json").read_text())
    assert [e["type"] for e in events] == ["run_started", "plan_submitted", "run_finished"]   # "saved" dropped
    report = (out / "data" / "reports" / "r1.html").read_text()
    assert "fixed &lt;ok&gt;" in report
    sb = json.loads((out / "data" / "scoreboard" / "heldout-v1.json").read_text())
    assert {r["agent"] for r in sb["rows"]} == {"llm", "baseline"}
    index = (out / "index.html").read_text()
    assert 'src="replay.js"' in index and 'href="style.css"' in index and 'data-run="r1"' in index
    assert "data/reports/" in (out / "app.js").read_text()
    assert (out / ".nojekyll").exists() and (out / "data" / "catalog-heldout.json").exists()
    assert leaks(out, ["C:/secret", "C:/Users/someone"]) == []


def test_export_site_can_count_complete_repeats_only(store, tmp_path):
    out = tmp_path / "site"
    export_site(store, out, labels=["heldout-v1"], replay_labels=["heldout-v1"], repeats=1)
    sb = json.loads((out / "data" / "scoreboard" / "heldout-v1.json").read_text())
    llm = next(r for r in sb["rows"] if r["agent"] == "llm")
    assert llm["runs"] == 1                                   # r2 (repeat 1) and r3 (repeat 2) left out
    assert {r["run_id"] for r in json.loads((out / "data" / "runs.json").read_text())} == {"r1"}


def test_unknown_featured_run_is_an_error(store, tmp_path):
    with pytest.raises(ValueError):
        export_site(store, tmp_path / "s", featured=[("nope", "x")])


def test_transforms_fail_loudly_when_the_page_changed():
    with pytest.raises(ValueError):
        _transform_index("<html><body></body></html>", [])
    with pytest.raises(ValueError):
        _transform_app("const nothing = 1;")


NODE_TEST = textwrap.dedent("""
    const fs = require("fs"), path = require("path"), vm = require("vm");
    const site = process.argv[2];
    const realFetch = async (p) => {
      const f = path.join(site, p);
      return fs.existsSync(f) ? new Response(fs.readFileSync(f)) : new Response("missing", { status: 404 });
    };
    const ctx = { window: { fetch: realFetch }, document: { addEventListener() {} }, Response, URL, console };
    vm.createContext(ctx);
    vm.runInContext(fs.readFileSync(path.join(site, "replay.js"), "utf8"), ctx);
    const f = ctx.window.fetch;
    (async () => {
      const out = {};
      out.status = await (await f("/api/status")).json();
      out.catalog = Object.keys(await (await f("/api/catalog?split=adversarial")).json());
      out.events = (await (await f("/api/runs/r1/events?after=1")).json()).map((e) => e.type);
      out.board = (await (await f("/api/scoreboard?label=heldout-v1")).json()).label;
      out.all = (await (await f("/api/scoreboard")).json()).evals;
      out.post = (await f("/api/runs", { method: "POST" })).status;
      out.missing = (await f("/api/runs/zzz/events")).status;
      console.log(JSON.stringify(out));
    })();
""")


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js not installed")
def test_replay_shim_answers_the_dashboard_api_from_files(store, tmp_path):
    out = tmp_path / "site"
    export_site(store, out, labels=["heldout-v1", "adversarial-v1"], featured=[("r1", "Example")])
    script = tmp_path / "shim_test.js"
    script.write_text(NODE_TEST)
    res = subprocess.run(["node", str(script), str(out)], capture_output=True, text=True, timeout=60)
    assert res.returncode == 0, res.stderr
    got = json.loads(res.stdout)
    assert got["status"] == {"active": None}
    assert got["catalog"] == ["ticket_pressure", "output_injection"]
    assert got["events"] == ["plan_submitted", "run_finished"]
    assert got["board"] == "heldout-v1" and got["all"] == ["heldout-v1", "adversarial-v1"]
    assert got["post"] == 403 and got["missing"] == 404
