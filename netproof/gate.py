"""Policy gate: deterministic checks on a change plan before anything runs.

No model is involved. A plan is allowed only if every rule passes.
"""
from __future__ import annotations

import ipaddress
import shlex
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

from .schemas import ChangePlan

MAX_COMMANDS = 5
SHELL_METACHARS = set(";&|<>`$\\\n\r")
IPTABLES_CHAINS = {"INPUT", "FORWARD", "OUTPUT"}
IPTABLES_TARGETS = {"ACCEPT", "DROP", "REJECT"}
IPTABLES_PROTOCOLS = {"tcp", "udp", "icmp"}
IPTABLES_MODULES = {"tcp", "udp", "icmp", "conntrack", "state"}
IPTABLES_FORBIDDEN = {
    "-F", "--flush", "-X", "--delete-chain", "-P", "--policy", "-Z", "--zero",
    "-N", "--new-chain", "-E", "--rename-chain", "-R", "--replace", "!",
}
MIN_ACCEPT_PREFIX = 16  # ACCEPT rules must name source and destination no broader than /16
MIN_ROUTE_PREFIX = 8
MIN_MTU, MAX_MTU = 1280, 9000


@dataclass
class GateContext:
    devices: Set[str]                 # every lab device
    scope: Set[str]                   # devices on the path of the reported flow
    ifaces: Dict[str, Set[str]]       # device -> interface names
    node_ips: Set[str]                # addresses of lab devices (allowed next hops)


@dataclass
class GateVerdict:
    allowed: bool
    violations: List[str] = field(default_factory=list)

    def summary(self) -> str:
        return "allowed" if self.allowed else "; ".join(self.violations)


def _net(value: str) -> Optional[ipaddress.IPv4Network]:
    try:
        return ipaddress.ip_network(value, strict=False)
    except ValueError:
        return None


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except ValueError:
        return False


def _check_ip_route(tok: List[str], device: str, ctx: GateContext) -> List[str]:
    if len(tok) < 4:
        return ["ip route: missing arguments"]
    verb = tok[2]
    if verb not in {"add", "replace", "del", "delete"}:
        return [f"ip route {verb}: only add, replace and del are allowed"]
    dst = tok[3]
    errs: List[str] = []
    if verb in {"del", "delete"} and (dst == "default" or (_net(dst) is not None and _net(dst).prefixlen == 0)):
        errs.append("ip route: deleting the default route is not allowed (use replace to change it)")
    if dst != "default":
        net = _net(dst)
        if net is None:
            errs.append(f"ip route: invalid destination {dst!r}")
        elif net.prefixlen == 0:
            pass  # 0.0.0.0/0 is the same as default
        elif net.prefixlen < MIN_ROUTE_PREFIX:
            errs.append(f"ip route: destination {dst} is broader than /{MIN_ROUTE_PREFIX}")
    i = 4
    while i < len(tok):
        key = tok[i]
        if i + 1 >= len(tok):
            errs.append(f"ip route: option {key!r} has no value")
            break
        val = tok[i + 1]
        if key == "via":
            if not _is_ip(val):
                errs.append(f"ip route: next hop {val!r} is not an address")
            elif val not in ctx.node_ips:
                errs.append(f"ip route: next hop {val} is not a lab device address")
        elif key == "dev":
            if val not in ctx.ifaces.get(device, set()):
                errs.append(f"ip route: interface {val!r} does not exist on {device}")
        elif key == "metric":
            if not val.isdigit():
                errs.append("ip route: metric must be a number")
        else:
            errs.append(f"ip route: option {key!r} is not allowed")
        i += 2
    if verb in {"add", "replace"} and "via" not in tok and "dev" not in tok:
        errs.append("ip route: add/replace needs 'via' or 'dev'")
    return errs


def _check_ip_link(tok: List[str], device: str, ctx: GateContext) -> List[str]:
    """Allowed: ip link set [dev] <iface> up | mtu <n> [up]."""
    usage = f"ip link: only 'ip link set <iface> up' or 'ip link set <iface> mtu <{MIN_MTU}-{MAX_MTU}> [up]'"
    args = tok[2:]
    if args[:1] != ["set"]:
        return [usage]
    args = args[1:]
    if args[:1] == ["dev"]:
        args = args[1:]
    if not args:
        return [usage]
    iface, rest = args[0], args[1:]
    errs: List[str] = []
    if iface not in ctx.ifaces.get(device, set()):
        errs.append(f"ip link: interface {iface!r} does not exist on {device}")
    if rest == ["up"]:
        return errs
    if len(rest) in (2, 3) and rest[0] == "mtu" and (len(rest) == 2 or rest[2] == "up"):
        if not rest[1].isdigit() or not (MIN_MTU <= int(rest[1]) <= MAX_MTU):
            errs.append(f"ip link: mtu must be a number from {MIN_MTU} to {MAX_MTU}")
        return errs
    return [usage]


def _check_ip_addr(tok: List[str], device: str, ctx: GateContext) -> List[str]:
    if len(tok) != 6 or tok[2] not in {"add", "del"} or tok[4] != "dev":
        return ["ip addr: only 'ip addr add|del <address/prefix> dev <iface>' is allowed"]
    errs = []
    net = _net(tok[3])
    if net is None or "/" not in tok[3]:
        errs.append(f"ip addr: {tok[3]!r} must be address/prefix")
    elif not (8 <= net.prefixlen <= 32):
        errs.append("ip addr: prefix length must be between 8 and 32")
    if tok[5] not in ctx.ifaces.get(device, set()):
        errs.append(f"ip addr: interface {tok[5]!r} does not exist on {device}")
    return errs


def _check_iptables(tok: List[str], device: str, ctx: GateContext) -> List[str]:
    args = tok[1:]
    errs: List[str] = []
    for a in args:
        if a in IPTABLES_FORBIDDEN:
            return [f"iptables: {a} is not allowed"]
    if args[:2] == ["-t", "filter"]:
        args = args[2:]
    elif "-t" in args or "--table" in args:
        return ["iptables: only the filter table is allowed"]
    if not args or args[0] not in {"-I", "-A", "-D", "--insert", "--append", "--delete"}:
        return ["iptables: only -I, -A or -D is allowed"]
    op = {"--insert": "-I", "--append": "-A", "--delete": "-D"}.get(args[0], args[0])
    if len(args) < 2 or args[1] not in IPTABLES_CHAINS:
        return [f"iptables: chain must be one of {sorted(IPTABLES_CHAINS)}"]
    rest = args[2:]
    if rest and rest[0].isdigit():
        if op == "-A":
            return ["iptables: -A does not take a rule number"]
        if op == "-D":
            return [] if len(rest) == 1 else ["iptables: -D with a rule number takes nothing else"]
        rest = rest[1:]
    opts: Dict[str, str] = {}
    i = 0
    while i < len(rest):
        key = rest[i]
        if i + 1 >= len(rest):
            errs.append(f"iptables: option {key!r} has no value")
            break
        val = rest[i + 1]
        norm = {"--source": "-s", "--destination": "-d", "--protocol": "-p", "--jump": "-j",
                "--destination-port": "--dport", "--source-port": "--sport",
                "--in-interface": "-i", "--out-interface": "-o", "--match": "-m"}.get(key, key)
        if norm in {"-s", "-d"}:
            if _net(val) is None:
                errs.append(f"iptables: {key} {val!r} is not an address or network")
        elif norm == "-p":
            if val not in IPTABLES_PROTOCOLS:
                errs.append(f"iptables: protocol {val!r} is not allowed")
        elif norm in {"--dport", "--sport"}:
            if not val.isdigit():
                errs.append(f"iptables: {key} must be a single port number")
        elif norm in {"-i", "-o"}:
            if val not in ctx.ifaces.get(device, set()):
                errs.append(f"iptables: interface {val!r} does not exist on {device}")
        elif norm == "-m":
            if val not in IPTABLES_MODULES:
                errs.append(f"iptables: match module {val!r} is not allowed")
        elif norm in {"--ctstate", "--state", "--icmp-type"}:
            pass
        elif norm == "-j":
            if val not in IPTABLES_TARGETS:
                errs.append(f"iptables: target {val!r} is not allowed")
        else:
            errs.append(f"iptables: option {key!r} is not allowed")
        opts[norm] = val
        i += 2
    if "-j" not in opts:
        errs.append("iptables: rule needs a target (-j ACCEPT, DROP or REJECT)")
    if op in {"-I", "-A"} and opts.get("-j") == "ACCEPT":
        for side, name in (("-s", "source"), ("-d", "destination")):
            net = _net(opts.get(side, ""))
            if side not in opts:
                errs.append(f"iptables: ACCEPT rules must name a {name} (-{side[1]})")
            elif net is not None and net.prefixlen < MIN_ACCEPT_PREFIX:
                errs.append(f"iptables: ACCEPT {name} {opts[side]} is broader than /{MIN_ACCEPT_PREFIX}")
    return errs


def check_command(cmd: str, device: str, ctx: GateContext) -> List[str]:
    if any(ch in SHELL_METACHARS for ch in cmd):
        return ["contains shell metacharacters"]
    try:
        tok = shlex.split(cmd)
    except ValueError as e:
        return [f"cannot parse: {e}"]
    if not tok:
        return ["empty command"]
    if tok[0] == "ip":
        if len(tok) < 3:
            return ["ip: missing arguments"]
        obj = tok[1]
        if obj in {"route", "r", "ro", "rou"}:
            return _check_ip_route(tok, device, ctx)
        if obj in {"link", "l", "li"}:
            return _check_ip_link(tok, device, ctx)
        if obj in {"addr", "address", "a"}:
            return _check_ip_addr(tok, device, ctx)
        return [f"ip {obj}: not allowed"]
    if tok[0] == "iptables":
        return _check_iptables(tok, device, ctx)
    if tok[0] == "sysctl":
        if tok == ["sysctl", "-w", "net.ipv4.ip_forward=1"]:
            return []
        return ["sysctl: only 'sysctl -w net.ipv4.ip_forward=1' is allowed"]
    return [f"command {tok[0]!r} is not allowed"]


def check_plan(plan: ChangePlan, ctx: GateContext) -> GateVerdict:
    v: List[str] = []
    if plan.device not in ctx.devices:
        return GateVerdict(False, [f"unknown device {plan.device!r}"])
    if plan.device not in ctx.scope:
        v.append(f"device {plan.device} is outside the scope of the reported problem "
                 f"(allowed: {', '.join(sorted(ctx.scope))})")
    if not (1 <= len(plan.commands) <= MAX_COMMANDS):
        v.append(f"plan must have 1 to {MAX_COMMANDS} commands (has {len(plan.commands)})")
    if not plan.rollback:
        v.append("plan must include rollback commands")
    for n, cmd in enumerate(plan.commands, start=1):
        v.extend(f"command {n} ({cmd!r}): {e}" for e in check_command(cmd, plan.device, ctx))
    return GateVerdict(allowed=not v, violations=v)


def build_context(topo, lab, flows_or_src, dst: Optional[str] = None) -> GateContext:
    """Scope = every device on the path of the given flows (usually the flows failing at the start).

    The Phase 1 form build_context(topo, lab, src, dst) still works: scope = the src-dst path.
    """
    if dst is not None:
        scope = topo.path_nodes(flows_or_src, dst)
    else:
        scope: Set[str] = set()
        for f in flows_or_src:
            scope |= topo.path_nodes(f.src, f.dst)
    return GateContext(
        devices=set(topo.nodes),
        scope=scope,
        ifaces={n: set(lab.ifaces(n)) for n in topo.nodes},
        node_ips=topo.node_ips(),
    )
