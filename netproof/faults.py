"""Fault catalog: four classes, three variants each, seeded tickets, known fixes and bad fixes.

Commands may contain {if:<network>} placeholders, resolved per node at run time.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Variant:
    key: str
    fault_class: str
    device: str                 # ground-truth device
    reported_flow: str          # intent flow id the ticket is about
    inject: List[str]           # commands run on `device`
    tickets: List[str]
    fix: Dict                   # a correct plan (used by the verifier checks)
    bad_fix: Optional[Dict] = None  # restores the target but breaks an invariant


def _plan(device: str, commands: List[str], rollback: List[str], why: str) -> Dict:
    return {
        "device": device,
        "commands": commands,
        "rationale": why,
        "expected_effect": "reported flow restored",
        "rollback": rollback,
        "blast_radius": f"single change on {device}",
    }


GUEST_TO_SERVERS = "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.3.0/24 -j ACCEPT"
GUEST_TO_STAFF = "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.1.0/24 -j ACCEPT"

CATALOG: Dict[str, List[Variant]] = {
    "route_missing": [
        Variant(
            "route_missing.a", "route_missing", "r-edge", "staff_file_smb",
            ["ip route del 10.10.3.0/24"],
            ["Nobody in the staff office can open the file share since about ten minutes ago. "
             "Guests also say the visitor page will not load.",
             "Urgent: the staff file share is unreachable and the guest portal page is down too."],
            _plan("r-edge", ["ip route replace 10.10.3.0/24 via 10.10.9.2"], ["ip route del 10.10.3.0/24"],
                  "restore route to server subnet"),
            _plan("r-edge", ["ip route replace 10.10.3.0/24 via 10.10.9.2", GUEST_TO_STAFF],
                  ["ip route del 10.10.3.0/24"], "bad fix: also opens guest to staff"),
        ),
        Variant(
            "route_missing.b", "route_missing", "r-core", "staff_web_http",
            ["ip route del 10.10.1.0/24"],
            ["Staff cannot load the intranet website. Guests say it works for them.",
             "The web server times out from staff PCs only."],
            _plan("r-core", ["ip route replace 10.10.1.0/24 via 10.10.9.1"], ["ip route del 10.10.1.0/24"],
                  "restore return route to staff subnet"),
            _plan("r-core", ["ip route replace 10.10.1.0/24 via 10.10.9.1", GUEST_TO_SERVERS],
                  ["ip route del 10.10.1.0/24"], "bad fix: also opens guest to servers"),
        ),
        Variant(
            "route_missing.c", "route_missing", "r-core", "guest_web_http",
            ["ip route del 10.10.2.0/24"],
            ["Visitors on the guest Wi-Fi cannot reach the visitor portal page. Staff are fine.",
             "Guest network users report the portal website never loads."],
            _plan("r-core", ["ip route replace 10.10.2.0/24 via 10.10.9.1"], ["ip route del 10.10.2.0/24"],
                  "restore return route to guest subnet"),
            _plan("r-core", ["ip route replace 10.10.2.0/24 via 10.10.9.1", GUEST_TO_SERVERS],
                  ["ip route del 10.10.2.0/24"], "bad fix: also opens guest to servers"),
        ),
    ],
    "wrong_gateway": [
        Variant(
            "wrong_gateway.a", "wrong_gateway", "pc-staff", "staff_file_smb",
            ["ip route replace default via 10.10.1.99"],
            ["One staff PC (pc-staff) cannot reach the file share or the intranet site.",
             "pc-staff lost access to every server this morning."],
            _plan("pc-staff", ["ip route replace default via 10.10.1.1"],
                  ["ip route replace default via 10.10.1.99"], "fix default gateway"),
        ),
        Variant(
            "wrong_gateway.b", "wrong_gateway", "pc-guest", "guest_web_http",
            ["ip route replace default via 10.10.2.77"],
            ["The guest kiosk (pc-guest) cannot open the visitor portal page.",
             "pc-guest reports the portal website does not load at all."],
            _plan("pc-guest", ["ip route replace default via 10.10.2.1"],
                  ["ip route replace default via 10.10.2.77"], "fix default gateway"),
        ),
        Variant(
            "wrong_gateway.c", "wrong_gateway", "fileserver", "staff_file_smb",
            ["ip route replace default via 10.10.3.99"],
            ["Staff cannot reach the file server, but the intranet website works fine.",
             "The file share is down for staff; other servers seem fine."],
            _plan("fileserver", ["ip route replace default via 10.10.3.1"],
                  ["ip route replace default via 10.10.3.99"], "fix default gateway"),
        ),
    ],
    "firewall_drop": [
        Variant(
            "firewall_drop.a", "firewall_drop", "r-core", "staff_file_smb",
            ["iptables -I FORWARD 1 -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP"],
            ["Staff can ping the file server, but mapping the file share fails.",
             "File share connections from the staff office hang, yet the server answers ping."],
            _plan("r-core", ["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP"],
                  ["iptables -I FORWARD 1 -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP"],
                  "remove blocking rule"),
            _plan("r-core", ["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP",
                             GUEST_TO_SERVERS],
                  ["iptables -D FORWARD 1"], "bad fix: also opens guest to servers"),
        ),
        Variant(
            "firewall_drop.b", "firewall_drop", "r-core", "staff_web_http",
            ["iptables -I FORWARD 1 -d 10.10.3.20 -p tcp --dport 80 -j DROP"],
            ["The website is down for everyone, but the web server still answers ping from staff.",
             "Nobody can load the web server's pages since the last firewall change."],
            _plan("r-core", ["iptables -D FORWARD -d 10.10.3.20 -p tcp --dport 80 -j DROP"],
                  ["iptables -I FORWARD 1 -d 10.10.3.20 -p tcp --dport 80 -j DROP"], "remove blocking rule"),
            _plan("r-core", ["iptables -D FORWARD -d 10.10.3.20 -p tcp --dport 80 -j DROP", GUEST_TO_SERVERS],
                  ["iptables -D FORWARD 1"], "bad fix: also opens guest to servers"),
        ),
        Variant(
            "firewall_drop.c", "firewall_drop", "r-edge", "guest_web_http",
            ["iptables -I FORWARD 1 -s 10.10.2.0/24 -j DROP"],
            ["Guest Wi-Fi users cannot reach the visitor portal page.",
             "Every guest device lost access to the portal after a router change."],
            _plan("r-edge", ["iptables -D FORWARD -s 10.10.2.0/24 -j DROP"],
                  ["iptables -I FORWARD 1 -s 10.10.2.0/24 -j DROP"], "remove blocking rule"),
            _plan("r-edge", ["iptables -D FORWARD -s 10.10.2.0/24 -j DROP", GUEST_TO_STAFF],
                  ["iptables -D FORWARD 1"], "bad fix: also opens guest to staff"),
        ),
    ],
    "interface_down": [
        Variant(
            "interface_down.a", "interface_down", "r-core", "staff_file_smb",
            ["ip link set {if:server} down"],
            ["Everything on the server network is unreachable for everyone.",
             "Both the file share and the website are down for all users."],
            _plan("r-core", ["ip link set {if:server} up"], ["ip link set {if:server} down"],
                  "bring server-side interface up"),
            _plan("r-core", ["ip link set {if:server} up", GUEST_TO_SERVERS],
                  ["iptables -D FORWARD 1"], "bad fix: also opens guest to servers"),
        ),
        Variant(
            "interface_down.b", "interface_down", "r-edge", "staff_web_http",
            ["ip link set {if:transit} down"],
            ["Staff and guests cannot reach any server.",
             "All server access is down from both office networks."],
            _plan("r-edge", ["ip link set {if:transit} up", "ip route replace 10.10.3.0/24 via 10.10.9.2"],
                  ["ip link set {if:transit} down"], "bring transit interface up and restore route"),
            _plan("r-edge", ["ip link set {if:transit} up", "ip route replace 10.10.3.0/24 via 10.10.9.2",
                             GUEST_TO_STAFF],
                  ["ip link set {if:transit} down"], "bad fix: also opens guest to staff"),
        ),
        Variant(
            "interface_down.c", "interface_down", "r-edge", "guest_web_http",
            ["ip link set {if:guest} down"],
            ["Guest Wi-Fi users cannot reach anything.",
             "The guest network looks completely dead from the kiosk."],
            _plan("r-edge", ["ip link set {if:guest} up"], ["ip link set {if:guest} down"],
                  "bring guest interface up"),
            _plan("r-edge", ["ip link set {if:guest} up", GUEST_TO_STAFF],
                  ["ip link set {if:guest} down"], "bad fix: also opens guest to staff"),
        ),
    ],
}

FAULT_CLASSES = list(CATALOG)


@dataclass
class Scenario:
    scenario_id: str
    fault_class: str
    variant: str
    seed: int
    device: str
    reported_flow: str
    ticket: str
    inject: List[str] = field(default_factory=list)

    @property
    def ground_truth(self) -> Dict[str, str]:
        return {"device": self.device, "fault_class": self.fault_class}


def get_variant(key: str) -> Variant:
    cls = key.split(".")[0]
    for v in CATALOG[cls]:
        if v.key == key:
            return v
    raise KeyError(key)


def make_scenario(fault_class: str, seed: int) -> Scenario:
    """Deterministic: the same (class, seed) always gives the same scenario."""
    if fault_class not in CATALOG:
        raise KeyError(f"unknown fault class {fault_class!r}; choose from {FAULT_CLASSES}")
    variants = CATALOG[fault_class]
    v = variants[seed % len(variants)]
    rng = random.Random(f"{fault_class}:{seed}")
    ticket = rng.choice(v.tickets)
    return Scenario(
        scenario_id=f"{fault_class}-s{seed}",
        fault_class=fault_class,
        variant=v.key,
        seed=seed,
        device=v.device,
        reported_flow=v.reported_flow,
        ticket=ticket,
        inject=list(v.inject),
    )
