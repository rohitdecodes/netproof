from netproof.tools import ToolBox, tool_schemas
from netproof.topology import load_topology
from tests.fakes import FakeLab

TOPO = load_topology()


def test_schemas_cover_tools_and_submit_plan():
    names = {s["function"]["name"] for s in tool_schemas(TOPO)}
    assert {"ping", "traceroute", "show_routes", "show_firewall", "test_flow", "submit_plan"} <= names


def test_unknown_device_is_an_error_not_a_crash():
    tb = ToolBox(FakeLab(), TOPO)
    assert tb.dispatch("show_routes", {"device": "r-cloud"}).startswith("ERROR")
    assert tb.dispatch("nope", {}).startswith("ERROR")
    assert tb.dispatch("ping", {"src": "pc-staff", "dst": "not-an-ip"}).startswith("ERROR")


def test_output_is_wrapped_as_device_data():
    out = ToolBox(FakeLab(), TOPO).dispatch("show_routes", {"device": "r-edge"})
    assert out.startswith('<device_output device="r-edge"') and out.endswith("</device_output>")
