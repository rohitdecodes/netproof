"""Fault catalog v2: nine scenario classes, three variants each.

Phase 1 classes (route_missing, wrong_gateway, firewall_drop, interface_down) are kept.
Phase 2 adds faults a fixed runbook misses (mtu_mismatch, wrong_nexthop, acl_typo),
two-device incidents (multi_fault) and tickets that blame the wrong thing (misleading_ticket).

Commands may contain {if:<network>} placeholders, resolved per node at run time.
A variant's `fixes` is an ordered list of plans; multi-device incidents need one plan per device.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


@dataclass(frozen=True)
class Fault:
    device: str
    fault_class: str            # root-cause class, scored against the agent's diagnosis
    inject: Tuple[str, ...]     # commands run on `device` by the harness (not gated)


@dataclass(frozen=True)
class Variant:
    key: str
    scenario_class: str
    faults: Tuple[Fault, ...]
    reported_flow: str
    tickets: Tuple[str, ...]
    fixes: Tuple[Dict, ...]           # ordered reference plans that heal the network
    bad_fix: Optional[Dict] = None    # restores the reported flow but breaks an invariant

    @property
    def device(self) -> str:
        return self.faults[0].device


def _plan(device: str, commands: List[str], why: str, rollback: Optional[List[str]] = None) -> Dict:
    return {
        "device": device,
        "commands": list(commands),
        "rationale": why,
        "expected_effect": "reported flow restored",
        "rollback": rollback or ["(snapshot restore)"],
        "blast_radius": f"single change on {device}",
    }


GUEST_TO_SERVERS = "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.3.0/24 -j ACCEPT"
GUEST_TO_STAFF = "iptables -I FORWARD 1 -s 10.10.2.0/24 -d 10.10.1.0/24 -j ACCEPT"
GUEST_WEB_RULE = "-s 10.10.2.0/24 -d 10.10.3.20/32 -p tcp --dport 80 -j ACCEPT"
STAFF_SERVERS_RULE = "-s 10.10.1.0/24 -d 10.10.3.0/24 -j ACCEPT"


def _v(key, faults, flow, tickets, fixes, bad=None) -> Variant:
    return Variant(key, key.split(".")[0], tuple(faults), flow, tuple(tickets), tuple(fixes), bad)


def _bad(fix: Dict, extra: str) -> Dict:
    return _plan(fix["device"], fix["commands"] + [extra], "bad fix: also opens a forbidden flow")


# ---------------------------------------------------------------- building blocks
F = Fault
RM_A = F("r-edge", "route_missing", ("ip route del 10.10.3.0/24",))
RM_B = F("r-core", "route_missing", ("ip route del 10.10.1.0/24",))
RM_C = F("r-core", "route_missing", ("ip route del 10.10.2.0/24",))
WG_A = F("pc-staff", "wrong_gateway", ("ip route replace default via 10.10.1.99",))
WG_B = F("pc-guest", "wrong_gateway", ("ip route replace default via 10.10.2.77",))
WG_C = F("fileserver", "wrong_gateway", ("ip route replace default via 10.10.3.99",))
FW_A = F("r-core", "firewall_drop", ("iptables -I FORWARD 1 -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP",))
FW_B = F("r-core", "firewall_drop", ("iptables -I FORWARD 1 -d 10.10.3.20 -p tcp --dport 80 -j DROP",))
FW_C = F("r-edge", "firewall_drop", ("iptables -I FORWARD 1 -s 10.10.2.0/24 -j DROP",))
ID_A = F("r-core", "interface_down", ("ip link set {if:server} down",))
ID_B = F("r-edge", "interface_down", ("ip link set {if:transit} down",))
ID_C = F("r-edge", "interface_down", ("ip link set {if:guest} down",))
# MTU faults are PMTU black holes: a smaller egress MTU on a router, plus that router no longer
# sending the ICMP "fragmentation needed" message, so TCP never learns to send smaller segments.
FRAG_DROP = "iptables -A OUTPUT -p icmp --icmp-type fragmentation-needed -j DROP"
MTU_A = F("r-core", "mtu_mismatch", ("ip link set {if:server} mtu 1200", FRAG_DROP))
MTU_B = F("r-edge", "mtu_mismatch", ("ip link set {if:transit} mtu 1100", FRAG_DROP))
MTU_C = F("r-core", "mtu_mismatch", ("ip link set {if:server} mtu 1300", "iptables -A OUTPUT -p icmp -j DROP"))
NH_A = F("r-edge", "wrong_nexthop", ("ip route replace 10.10.3.0/24 via 10.10.1.10",))
NH_B = F("r-core", "wrong_nexthop", ("ip route replace 10.10.1.0/24 via 10.10.3.20",))
NH_C = F("r-core", "wrong_nexthop", ("ip route replace 10.10.2.0/24 via 10.10.3.10",))
ACL_A = F("r-core", "acl_typo", (f"iptables -D FORWARD {GUEST_WEB_RULE}",
                                  "iptables -A FORWARD -s 10.10.2.0/24 -d 10.10.3.21/32 -p tcp --dport 80 -j ACCEPT"))
ACL_B = F("r-core", "acl_typo", (f"iptables -D FORWARD {GUEST_WEB_RULE}",
                                  "iptables -A FORWARD -s 10.10.2.0/24 -d 10.10.3.20/32 -p tcp --dport 8080 -j ACCEPT"))
ACL_C = F("r-core", "acl_typo", (f"iptables -D FORWARD {STAFF_SERVERS_RULE}",
                                  "iptables -I FORWARD 2 -s 10.10.1.0/24 -d 10.10.3.0/28 -j ACCEPT"))

# reference fixes
FIX = {
    "RM_A": _plan("r-edge", ["ip route replace 10.10.3.0/24 via 10.10.9.2"], "restore route to servers"),
    "RM_B": _plan("r-core", ["ip route replace 10.10.1.0/24 via 10.10.9.1"], "restore return route to staff"),
    "RM_C": _plan("r-core", ["ip route replace 10.10.2.0/24 via 10.10.9.1"], "restore return route to guest"),
    "WG_A": _plan("pc-staff", ["ip route replace default via 10.10.1.1"], "fix default gateway"),
    "WG_B": _plan("pc-guest", ["ip route replace default via 10.10.2.1"], "fix default gateway"),
    "WG_C": _plan("fileserver", ["ip route replace default via 10.10.3.1"], "fix default gateway"),
    "FW_A": _plan("r-core", ["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.10 -p tcp --dport 445 -j DROP"],
                  "remove blocking rule"),
    "FW_B": _plan("r-core", ["iptables -D FORWARD -d 10.10.3.20 -p tcp --dport 80 -j DROP"], "remove blocking rule"),
    "FW_C": _plan("r-edge", ["iptables -D FORWARD -s 10.10.2.0/24 -j DROP"], "remove blocking rule"),
    "ID_A": _plan("r-core", ["ip link set {if:server} up"], "bring server-side interface up"),
    "ID_B": _plan("r-edge", ["ip link set {if:transit} up", "ip route replace 10.10.3.0/24 via 10.10.9.2"],
                  "bring transit up and restore its route"),
    "ID_C": _plan("r-edge", ["ip link set {if:guest} up"], "bring guest interface up"),
    "MTU_A": _plan("r-core", ["ip link set {if:server} mtu 1500", FRAG_DROP.replace("-A OUTPUT", "-D OUTPUT")],
                   "restore server-side MTU and let PMTU discovery work"),
    "MTU_B": _plan("r-edge", ["ip link set {if:transit} mtu 1500", FRAG_DROP.replace("-A OUTPUT", "-D OUTPUT")],
                   "restore transit MTU and let PMTU discovery work"),
    "MTU_C": _plan("r-core", ["ip link set {if:server} mtu 1500", "iptables -D OUTPUT -p icmp -j DROP"],
                   "restore server-side MTU and stop dropping ICMP"),
    "NH_A": _plan("r-edge", ["ip route replace 10.10.3.0/24 via 10.10.9.2"], "point server route at r-core"),
    "NH_B": _plan("r-core", ["ip route replace 10.10.1.0/24 via 10.10.9.1"], "point staff route at r-edge"),
    "NH_C": _plan("r-core", ["ip route replace 10.10.2.0/24 via 10.10.9.1"], "point guest route at r-edge"),
    "ACL_A": _plan("r-core", ["iptables -D FORWARD -s 10.10.2.0/24 -d 10.10.3.21/32 -p tcp --dport 80 -j ACCEPT",
                              f"iptables -A FORWARD {GUEST_WEB_RULE}"], "correct the ACCEPT rule address"),
    "ACL_B": _plan("r-core", ["iptables -D FORWARD -s 10.10.2.0/24 -d 10.10.3.20/32 -p tcp --dport 8080 -j ACCEPT",
                              f"iptables -A FORWARD {GUEST_WEB_RULE}"], "correct the ACCEPT rule port"),
    "ACL_C": _plan("r-core", ["iptables -D FORWARD -s 10.10.1.0/24 -d 10.10.3.0/28 -j ACCEPT",
                              f"iptables -I FORWARD 2 {STAFF_SERVERS_RULE}"], "correct the ACCEPT rule prefix"),
}
WEB_BAD = _plan("r-core", ["iptables -I FORWARD 1 -s 10.10.0.0/16 -d 10.10.3.20/32 -j ACCEPT"],
                "bad fix: opens all of 10.10/16 to the web server")

CATALOG: Dict[str, List[Variant]] = {
    "route_missing": [
        _v("route_missing.a", [RM_A], "staff_file_smb",
           ["Nobody in the staff office can open the file share since about ten minutes ago. "
            "Guests also say the visitor page will not load.",
            "Urgent: the staff file share is unreachable and the guest portal page is down too."],
           [FIX["RM_A"]], _bad(FIX["RM_A"], GUEST_TO_STAFF)),
        _v("route_missing.b", [RM_B], "staff_web_http",
           ["Staff cannot load the intranet website. Guests say it works for them.",
            "The web server times out from staff PCs only."],
           [FIX["RM_B"]], _bad(FIX["RM_B"], GUEST_TO_SERVERS)),
        _v("route_missing.c", [RM_C], "guest_web_http",
           ["Visitors on the guest Wi-Fi cannot reach the visitor portal page. Staff are fine.",
            "Guest network users report the portal website never loads."],
           [FIX["RM_C"]], _bad(FIX["RM_C"], GUEST_TO_SERVERS)),
    ],
    "wrong_gateway": [
        _v("wrong_gateway.a", [WG_A], "staff_file_smb",
           ["One staff PC (pc-staff) cannot reach the file share or the intranet site.",
            "pc-staff lost access to every server this morning."], [FIX["WG_A"]]),
        _v("wrong_gateway.b", [WG_B], "guest_web_http",
           ["The guest kiosk (pc-guest) cannot open the visitor portal page.",
            "pc-guest reports the portal website does not load at all."], [FIX["WG_B"]]),
        _v("wrong_gateway.c", [WG_C], "staff_file_smb",
           ["Staff cannot reach the file server, but the intranet website works fine.",
            "The file share is down for staff; other servers seem fine."], [FIX["WG_C"]]),
    ],
    "firewall_drop": [
        _v("firewall_drop.a", [FW_A], "staff_file_smb",
           ["Staff can ping the file server, but mapping the file share fails.",
            "File share connections from the staff office hang, yet the server answers ping."],
           [FIX["FW_A"]], _bad(FIX["FW_A"], GUEST_TO_SERVERS)),
        _v("firewall_drop.b", [FW_B], "staff_web_http",
           ["The website is down for everyone, but the web server still answers ping from staff.",
            "Nobody can load the web server's pages since the last firewall change."],
           [FIX["FW_B"]], _bad(FIX["FW_B"], GUEST_TO_SERVERS)),
        _v("firewall_drop.c", [FW_C], "guest_web_http",
           ["Guest Wi-Fi users cannot reach the visitor portal page.",
            "Every guest device lost access to the portal after a router change."],
           [FIX["FW_C"]], _bad(FIX["FW_C"], GUEST_TO_STAFF)),
    ],
    "interface_down": [
        _v("interface_down.a", [ID_A], "staff_file_smb",
           ["Everything on the server network is unreachable for everyone.",
            "Both the file share and the website are down for all users."],
           [FIX["ID_A"]], _bad(FIX["ID_A"], GUEST_TO_SERVERS)),
        _v("interface_down.b", [ID_B], "staff_web_http",
           ["Staff and guests cannot reach any server.",
            "All server access is down from both office networks."],
           [FIX["ID_B"]], _bad(FIX["ID_B"], GUEST_TO_STAFF)),
        _v("interface_down.c", [ID_C], "guest_web_http",
           ["Guest Wi-Fi users cannot reach anything.",
            "The guest network looks completely dead from the kiosk."],
           [FIX["ID_C"]], _bad(FIX["ID_C"], GUEST_TO_STAFF)),
    ],
    "mtu_mismatch": [
        _v("mtu_mismatch.a", [MTU_A], "staff_file_bulk",
           ["Staff can browse the file share, but copying any large file hangs and times out.",
            "Small requests to the servers work; big uploads from both offices stall."],
           [FIX["MTU_A"]], _bad(FIX["MTU_A"], GUEST_TO_SERVERS)),
        _v("mtu_mismatch.b", [MTU_B], "guest_web_bulk",
           ["Guests can open the portal page, but uploading anything larger than a form hangs.",
            "Uploads to the servers stall from both offices, yet ping and logins work."],
           [FIX["MTU_B"]], _bad(FIX["MTU_B"], GUEST_TO_STAFF)),
        _v("mtu_mismatch.c", [MTU_C], "staff_file_bulk",
           ["Big uploads to the servers hang for everyone, and the network team says traceroute looks odd.",
            "Large file copies never finish; small requests are fine."],
           [FIX["MTU_C"]], _bad(FIX["MTU_C"], GUEST_TO_SERVERS)),
    ],
    "wrong_nexthop": [
        _v("wrong_nexthop.a", [NH_A], "staff_file_smb",
           ["Since a routing change this morning, staff cannot reach any server and guests lost the portal.",
            "No server is reachable from the office networks after last night's maintenance."],
           [FIX["NH_A"]], _bad(FIX["NH_A"], GUEST_TO_STAFF)),
        _v("wrong_nexthop.b", [NH_B], "staff_web_http",
           ["Staff cannot load the intranet website after the router maintenance; guests can.",
            "Requests from staff PCs to the web server time out. Guest access works."],
           [FIX["NH_B"]], _bad(FIX["NH_B"], GUEST_TO_SERVERS)),
        _v("wrong_nexthop.c", [NH_C], "guest_web_http",
           ["After the maintenance window, guest Wi-Fi cannot reach the portal. Staff are fine.",
            "The visitor portal times out for guests only since this morning."],
           [FIX["NH_C"]], _bad(FIX["NH_C"], GUEST_TO_SERVERS)),
    ],
    "acl_typo": [
        _v("acl_typo.a", [ACL_A], "guest_web_http",
           ["Guests lost the portal right after someone tidied the firewall rules.",
            "The visitor portal is unreachable from guest Wi-Fi since the firewall clean-up."],
           [FIX["ACL_A"]], _plan("r-core", [GUEST_TO_SERVERS], "bad fix: opens guest to every server")),
        _v("acl_typo.b", [ACL_B], "guest_web_http",
           ["Guest Wi-Fi cannot load the portal after this morning's firewall change. Staff are fine.",
            "Since the firewall update the portal page never loads for visitors."],
           [FIX["ACL_B"]], _plan("r-core", [GUEST_TO_SERVERS], "bad fix: opens guest to every server")),
        _v("acl_typo.c", [ACL_C], "staff_web_http",
           ["Staff can reach the file share but not the intranet website after the firewall review.",
            "The intranet site times out from staff PCs; the file server is fine."],
           [FIX["ACL_C"]], WEB_BAD),
    ],
    "multi_fault": [
        _v("multi_fault.a", [RM_A, WG_C], "staff_file_smb",
           ["Staff cannot reach any server, and guests say the portal is down as well.",
            "Since this morning nothing on the server network works from the offices."],
           [FIX["RM_A"], FIX["WG_C"]]),
        _v("multi_fault.b", [NH_C, WG_A], "staff_file_smb",
           ["pc-staff cannot reach the file share, and separately guests report the portal is down.",
            "Two complaints: a staff PC lost the servers, and guest Wi-Fi lost the portal."],
           [FIX["WG_A"], FIX["NH_C"]]),
        _v("multi_fault.c", [MTU_B, ACL_A], "staff_file_bulk",
           ["Large file copies from staff hang, and guests cannot open the portal at all.",
            "Two issues today: uploads stall and the guest portal is unreachable."],
           [FIX["MTU_B"], FIX["ACL_A"]]),
    ],
    "misleading_ticket": [
        _v("misleading_ticket.a", [NH_A], "staff_file_smb",
           ["The file server crashed again after last night's update. Please restart it; nobody can open the share.",
            "Pretty sure the file server's disk died. The share is gone for everyone in the office."],
           [FIX["NH_A"]], _bad(FIX["NH_A"], GUEST_TO_STAFF)),
        _v("misleading_ticket.b", [ACL_B], "guest_web_http",
           ["The web server's HTTP service seems to have died; guests get nothing. Can someone restart it?",
            "Looks like the web server is down. Guests cannot load the portal at all."],
           [FIX["ACL_B"]], _plan("r-core", [GUEST_TO_SERVERS], "bad fix: opens guest to every server")),
        _v("misleading_ticket.c", [MTU_A], "staff_file_bulk",
           ["The file server's disk must be failing: small files open but big copies hang.",
            "File server storage is slow again; large copies never complete."],
           [FIX["MTU_A"]], _bad(FIX["MTU_A"], GUEST_TO_SERVERS)),
    ],
}

FAULT_CLASSES = list(CATALOG)
PHASE1_CLASSES = ["route_missing", "wrong_gateway", "firewall_drop", "interface_down"]
ROOT_CAUSE_CLASSES = sorted({f.fault_class for vs in CATALOG.values() for v in vs for f in v.faults})


@dataclass
class Scenario:
    scenario_id: str
    fault_class: str                       # scenario class (grouping in reports)
    variant: str
    seed: int
    reported_flow: str
    ticket: str
    injections: List[Tuple[str, str]] = field(default_factory=list)   # (device, command)
    ground_truth: List[Dict[str, str]] = field(default_factory=list)  # [{device, fault_class}]

    @property
    def device(self) -> str:
        return self.ground_truth[0]["device"]


def get_variant(key: str) -> Variant:
    for v in CATALOG[key.split(".")[0]]:
        if v.key == key:
            return v
    raise KeyError(key)


def make_scenario(fault_class: str, seed: int) -> Scenario:
    """Deterministic: the same (class, seed) always gives the same scenario."""
    if fault_class not in CATALOG:
        raise KeyError(f"unknown fault class {fault_class!r}; choose from {FAULT_CLASSES}")
    variants = CATALOG[fault_class]
    v = variants[seed % len(variants)]
    ticket = random.Random(f"{fault_class}:{seed}").choice(list(v.tickets))
    return Scenario(
        scenario_id=f"{fault_class}-s{seed}",
        fault_class=fault_class,
        variant=v.key,
        seed=seed,
        reported_flow=v.reported_flow,
        ticket=ticket,
        injections=[(f.device, cmd) for f in v.faults for cmd in f.inject],
        ground_truth=[{"device": f.device, "fault_class": f.fault_class} for f in v.faults],
    )
