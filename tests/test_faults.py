from netproof.faults import CATALOG, FAULT_CLASSES, make_scenario
from netproof.intent import load_intent
from netproof.topology import load_topology

TOPO = load_topology()
FLOWS = {f.id: f for f in load_intent()}


def test_scenarios_are_deterministic():
    for c in FAULT_CLASSES:
        assert make_scenario(c, 7).ticket == make_scenario(c, 7).ticket


def test_every_variant_has_two_tickets_and_known_flow():
    for variants in CATALOG.values():
        assert len(variants) == 3
        for v in variants:
            assert len(v.tickets) >= 2 and v.reported_flow in FLOWS and v.device in TOPO.nodes
