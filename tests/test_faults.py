from netproof.faults import CATALOG, FAULT_CLASSES, PHASE1_CLASSES, ROOT_CAUSE_CLASSES, make_scenario
from netproof.intent import load_intent
from netproof.schemas import FAULT_CLASS_CHOICES
from netproof.topology import load_topology

TOPO = load_topology()
FLOWS = {f.id: f for f in load_intent()}


def test_scenarios_are_deterministic():
    for c in FAULT_CLASSES:
        assert make_scenario(c, 7).ticket == make_scenario(c, 7).ticket


def test_catalog_shape():
    assert len(FAULT_CLASSES) == 9 and set(PHASE1_CLASSES) <= set(FAULT_CLASSES)
    for variants in CATALOG.values():
        assert len(variants) == 3
        for v in variants:
            assert len(v.tickets) >= 2 and v.reported_flow in FLOWS
            assert all(f.device in TOPO.nodes for f in v.faults)
            assert len(v.fixes) >= 1 and all(fx["device"] in TOPO.nodes for fx in v.fixes)


def test_multi_fault_variants_span_two_devices_with_one_fix_each():
    for v in CATALOG["multi_fault"]:
        assert len({f.device for f in v.faults}) == 2
        assert {fx["device"] for fx in v.fixes} == {f.device for f in v.faults}


def test_scenario_carries_all_injections_and_ground_truth():
    sc = make_scenario("multi_fault", 0)
    assert len(sc.ground_truth) == 2
    assert {d for d, _ in sc.injections} == {g["device"] for g in sc.ground_truth}


def test_every_root_cause_class_is_a_valid_diagnosis_choice():
    assert set(ROOT_CAUSE_CLASSES) | {"other"} == set(FAULT_CLASS_CHOICES)


def test_misleading_tickets_reuse_hard_faults():
    for v in CATALOG["misleading_ticket"]:
        assert v.faults[0].fault_class in {"wrong_nexthop", "acl_typo", "mtu_mismatch"}
