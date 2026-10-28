"""Fault injection against the real Docker lab. Run with:  NP_DOCKER=1 pytest -m docker -v"""
import os

import pytest

from netproof.faults import CATALOG, make_scenario
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


@pytest.mark.parametrize("fault,seed", [(c, i) for c in CATALOG for i in range(3)])
def test_each_variant_breaks_its_flow_and_reset_heals(env, fault, seed):
    topo, lab, flows = env
    sc = make_scenario(fault, seed)
    lab.reset()
    for cmd in sc.inject:
        r = lab.run_command(sc.device, lab.resolve_placeholders(sc.device, cmd))
        assert r.ok, r.text()
    res = evaluate(lab, flows)
    assert not res[sc.reported_flow].ok, f"{sc.variant}: fault did not break {sc.reported_flow}"
    lab.reset()
    assert is_healthy(evaluate(lab, flows)), f"{sc.variant}: reset did not heal"
