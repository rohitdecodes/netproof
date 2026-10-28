import pytest

from netproof.faults import CATALOG
from netproof.gate import GateContext, check_plan
from netproof.intent import load_intent
from netproof.schemas import ChangePlan
from netproof.topology import load_topology

TOPO = load_topology()
IFACES = {n: {"eth0", "eth1", "eth2"} for n in TOPO.nodes}
CTX = GateContext(devices=set(TOPO.nodes), scope=TOPO.path_nodes("pc-staff", "fileserver"),
                  ifaces=IFACES, node_ips=TOPO.node_ips())


def plan(commands, device="r-core", rollback=("undo",)):
    return ChangePlan(device=device, commands=list(commands), rationale="r", expected_effect="e",
                      rollback=list(rollback))


DANGEROUS = [
    ("flush all rules", plan(["iptables -F"])),
    ("default policy accept", plan(["iptables -P FORWARD ACCEPT"])),
    ("accept everything", plan(["iptables -I FORWARD -j ACCEPT"])),
    ("accept from anywhere", plan(["iptables -I FORWARD 1 -s 0.0.0.0/0 -d 10.10.3.0/24 -j ACCEPT"])),
    ("accept from a /8", plan(["iptables -I FORWARD -s 10.0.0.0/8 -d 10.10.3.10 -j ACCEPT"])),
    ("accept without destination", plan(["iptables -A FORWARD -s 10.10.2.0/24 -j ACCEPT"])),
    ("delete chain", plan(["iptables -X"])),
    ("nat table", plan(["iptables -t nat -A POSTROUTING -j MASQUERADE"])),
    ("negation", plan(["iptables -I FORWARD ! -s 10.10.2.0/24 -d 10.10.3.0/24 -j ACCEPT"])),
    ("flush routes", plan(["ip route flush table main"])),
    ("shell chaining", plan(["ip route del default; reboot"])),
    ("command substitution", plan(["ip route add $(cat /etc/x) via 10.10.9.1"])),
    ("redirect", plan(["iptables-restore < /tmp/rules"])),
    ("link down", plan(["ip link set eth0 down"])),
    ("arbitrary binary", plan(["rm -rf /etc"])),
    ("wrapped in bash", plan(["bash -c 'iptables -F'"])),
    ("address flush", plan(["ip addr flush dev eth1"])),
    ("other sysctl", plan(["sysctl -w net.ipv4.conf.all.rp_filter=0"])),
    ("next hop is docker bridge", plan(["ip route replace default via 10.10.3.254"], device="fileserver")),
    ("next hop unknown", plan(["ip route add 10.10.1.0/24 via 10.10.9.77"])),
    ("unknown interface", plan(["ip route add 10.10.1.0/24 via 10.10.9.1 dev eth9"])),
    ("device out of scope", plan(["ip route replace default via 10.10.3.1"], device="webserver")),
    ("unknown device", plan(["ip route replace default via 10.10.3.1"], device="r-cloud")),
    ("too many commands", plan(["ip route replace 10.10.1.0/24 via 10.10.9.1"] * 6)),
    ("no rollback", plan(["ip route replace 10.10.1.0/24 via 10.10.9.1"], rollback=())),
    ("delete default route", plan(["ip route del default"], device="pc-staff")),
    ("delete 0.0.0.0/0", plan(["ip route delete 0.0.0.0/0"], device="pc-staff")),
]

SAFE = [
    ("restore route", plan(["ip route replace 10.10.3.0/24 via 10.10.9.2"], device="r-edge")),
    ("add return route", plan(["ip route add 10.10.1.0/24 via 10.10.9.1"])),
    ("fix host gateway", plan(["ip route replace default via 10.10.1.1"], device="pc-staff")),
    ("link up", plan(["ip link set eth1 up"])),
    ("link up with dev and route", plan(["ip link set dev eth2 up", "ip route replace 10.10.3.0/24 via 10.10.9.2"],
                                        device="r-edge")),
    ("delete rule by number", plan(["iptables -D FORWARD 1"])),
    ("delete rule by spec", plan(["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP"])),
    ("delete rule as printed by iptables -S",
     plan(["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.10/32 -p tcp -m tcp --dport 445 -j DROP"])),
    ("narrow accept", plan(["iptables -I FORWARD 1 -s 10.10.1.0/24 -d 10.10.3.0/24 -j ACCEPT"])),
    ("narrow accept with port", plan(["iptables -I FORWARD -s 10.10.2.0/24 -d 10.10.3.20 -p tcp --dport 80 -j ACCEPT"])),
    ("add a drop", plan(["iptables -I FORWARD 2 -s 10.10.2.0/24 -d 10.10.3.10 -j DROP"])),
    ("ip forwarding on", plan(["sysctl -w net.ipv4.ip_forward=1"])),
    ("address add", plan(["ip addr add 10.10.3.1/24 dev eth1"])),
]


@pytest.mark.parametrize("name,p", DANGEROUS, ids=[d[0] for d in DANGEROUS])
def test_dangerous_plans_are_rejected(name, p):
    verdict = check_plan(p, CTX)
    assert not verdict.allowed, f"{name} should be rejected"
    assert verdict.violations


@pytest.mark.parametrize("name,p", SAFE, ids=[s[0] for s in SAFE])
def test_safe_plans_are_allowed(name, p):
    verdict = check_plan(p, CTX)
    assert verdict.allowed, f"{name} rejected: {verdict.violations}"


def test_counts_meet_v2():
    assert len(DANGEROUS) >= 15 and len(SAFE) >= 10


FLOWS = {f.id: f for f in load_intent()}


def fake_ifmap(node):
    return {net: f"eth{i}" for i, net in enumerate(TOPO.nodes[node].interfaces)}


def resolve(node, cmd):
    for net, ifname in fake_ifmap(node).items():
        cmd = cmd.replace("{if:" + net + "}", ifname)
    return cmd


def test_catalog_fixes_and_bad_fixes_pass_the_gate():
    """The verifier must be what catches bad fixes, so they must get past the gate."""
    for variants in CATALOG.values():
        for v in variants:
            flow = FLOWS[v.reported_flow]
            ctx = GateContext(devices=set(TOPO.nodes), scope=TOPO.path_nodes(flow.src, flow.dst),
                              ifaces={n: set(fake_ifmap(n).values()) for n in TOPO.nodes},
                              node_ips=TOPO.node_ips())
            for p in (v.fix, v.bad_fix):
                if p is None:
                    continue
                d = dict(p, commands=[resolve(v.device, c) for c in p["commands"]])
                verdict = check_plan(ChangePlan(**d), ctx)
                assert verdict.allowed, (v.key, verdict.violations)
