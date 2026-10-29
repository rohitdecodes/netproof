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
    lab.run_command("r-core", lab.resolve_placeholders("r-core", "ip link set {if:server} mtu 1200"))
    assert not lab.snapshots_equal(lab.snapshot("r-core"), snap)
    errors = lab.restore("r-core", snap)
    assert errors == []
    assert lab.snapshots_equal(lab.snapshot("r-core"), snap)


def test_hosts_do_not_forward(env):
    topo, lab, _ = env
    for host in ("pc-staff", "pc-guest", "fileserver", "webserver"):
        assert lab.exec(host, ["sysctl", "-n", "net.ipv4.ip_forward"]).out.strip() == "0", host


def test_bulk_flow_detects_a_pmtu_black_hole(env):
    from netproof.intent import Flow

    topo, lab, _ = env
    lab.reset()
    bulk = Flow("t", "pc-staff", "fileserver", "tcp-bulk", 445, "allow")
    small = Flow("t2", "pc-staff", "fileserver", "tcp", 445, "allow")
    assert lab.run_flow(bulk)
    lab.run_command("r-core", lab.resolve_placeholders("r-core", "ip link set {if:server} mtu 1200"))
    lab.run_command("r-core", "iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP")
    assert lab.run_flow(small), "small connections must still work"
    assert not lab.run_flow(bulk), "64 KB transfer must fail through the black hole"
    lab.reset()
    assert lab.run_flow(bulk), "reset must heal the MTU and flush learned path MTUs"
