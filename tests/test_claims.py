import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("check_claims", Path(__file__).parent.parent / "scripts" / "check_claims.py")
cc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cc)


def test_clean_text_passes(tmp_path):
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "results.md").write_text("x")
    text = "Fixed 52/54 runs. See [results](docs/results.md) and [site](https://example.org).\n"
    assert cc.check(text, tmp_path, results="| 52/54 (0.96) |") == []


def test_problems_are_reported(tmp_path):
    text = "\n".join([
        "Our production-ready agent fixes 100% of faults.",
        "Plan: [plan](docs/phase_3.md) and [gone](docs/missing.md)",
        "Fixed 9/10 runs.",
        "Verifier: 27/27 reference fixes. <!-- claims:ok -->",
        "Route 10.10.1.0/24 is fine.",
        "```",
        "100% inside a code block is ignored",
        "```",
    ])
    probs = cc.check(text, tmp_path, results="nothing here")
    joined = "\n".join(probs)
    assert "production" in joined and "100" in joined
    assert "local-only plan file" in joined and "does not exist: docs/missing.md" in joined
    assert "9/10 is not in the results file" in joined
    assert "27/27" not in joined and "0/24" not in joined and "line 7" not in joined


def test_emoji_is_flagged(tmp_path):
    assert any("emoji" in p for p in cc.check("Ship it \U0001F680\n", tmp_path))


def test_unfilled_placeholders_fail(tmp_path):
    probs = cc.check("Fixed <fill from results> runs. TODO add video link.\n", tmp_path)
    assert len(probs) == 2
