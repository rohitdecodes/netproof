"""Integration tests against the real Docker lab. Run with:  NP_DOCKER=1 pytest -m docker -v"""
import os

import pytest

from netproof.intent import evaluate, is_healthy, load_intent
from netproof.topology import load_topology

pytestmark = [
    pytest.mark.docker,
    pytest.mark.skipif(os.environ.get("NP_DOCKER") != "1", reason="set NP_DOCKER=1 with the lab running"),
]


@pytest.fixture(scope="module")
def env():
    from netproof.lab import DockerLab

    topo = load_topology()
    lab = DockerLab(topo)
    lab.reset()
    yield topo, lab, load_intent()
    lab.reset()


def test_baseline_is_healthy(env):
    topo, lab, flows = env
    lab.reset()
    res = evaluate(lab, flows)
    bad = [r.flow.id for r in res.values() if not r.ok]
    assert is_healthy(res), f"flows not matching intent at baseline: {bad}"


def test_reset_is_idempotent(env):
    topo, lab, _ = env
    lab.reset()
    first = {n: lab.snapshot(n) for n in topo.nodes}
    lab.reset()
    second = {n: lab.snapshot(n) for n in topo.nodes}
    for n in topo.nodes:
        assert lab.snapshots_equal(first[n], second[n]), n


def test_snapshot_restore_round_trip(env):
    topo, lab, _ = env
    lab.reset()
    snap = lab.snapshot("r-core")
    lab.run_command("r-core", "ip route del 10.10.1.0/24")
    lab.run_command("r-core", "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.3.0/24 -j ACCEPT")
    assert not lab.snapshots_equal(lab.snapshot("r-core"), snap)
    errors = lab.restore("r-core", snap)
    assert errors == []
    assert lab.snapshots_equal(lab.snapshot("r-core"), snap)
