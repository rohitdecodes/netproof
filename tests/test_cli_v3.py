from netproof.cli import _classes, _seeds, main, needs_freeze


def test_freeze_applies_only_to_model_runs_on_protected_splits():
    assert needs_freeze("heldout", "llm") and needs_freeze("adversarial", "router")
    assert not needs_freeze("heldout", "baseline") and not needs_freeze("dev", "llm")


def test_class_groups_per_split():
    assert len(_classes("all", "heldout")) == 9
    assert _classes("all", "adversarial") == ["ticket_pressure", "output_injection"]
    assert "mtu_mismatch" in _classes("new", "heldout") and "route_missing" not in _classes("new", "heldout")


def test_seed_ranges():
    assert _seeds("0-2") == [0, 1, 2] and _seeds("0,5,7-8") == [0, 5, 7, 8]


def test_scenarios_command_lists_a_split(capsys):
    assert main(["scenarios", "--split", "adversarial"]) == 0
    out = capsys.readouterr().out
    assert "adversarial-output_injection-s2" in out and "truth=" in out
