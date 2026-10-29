"""Controls the Docker lab: runs commands in containers, provisions the baseline,
snapshots and restores device state, and runs flow tests.

All commands are passed to `docker exec` as an argument list, never through a shell
built from model output.
"""
from __future__ import annotations

import json
import re
import shlex
import subprocess
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Dict, List, Optional

from .intent import Flow
from .topology import Topology


class LabError(RuntimeError):
    pass


@dataclass
class ExecResult:
    code: int
    out: str
    err: str

    @property
    def ok(self) -> bool:
        return self.code == 0

    def text(self) -> str:
        return (self.out + ("\n" + self.err if self.err.strip() else "")).strip()


_COUNTERS = re.compile(r"\[\d+:\d+\]")


def normalize_iptables(save_text: str) -> str:
    """Drops comments and packet counters so two iptables-save outputs can be compared."""
    lines = []
    for line in save_text.splitlines():
        if line.startswith("#") or not line.strip():
            continue
        lines.append(_COUNTERS.sub("[0:0]", line))
    return "\n".join(lines)


def _route_args(route: dict) -> List[str]:
    args = [route.get("dst", "default")]
    if route.get("gateway"):
        args += ["via", route["gateway"]]
    if route.get("dev"):
        args += ["dev", route["dev"]]
    return args


class DockerLab:
    def __init__(self, topo: Topology, prefix: str = "np-", timeout: int = 20):
        self.topo = topo
        self.prefix = prefix
        self.timeout = timeout
        self._ifmap: Dict[str, Dict[str, str]] = {}

    # ---- low level --------------------------------------------------------
    def container(self, node: str) -> str:
        if node not in self.topo.nodes:
            raise LabError(f"unknown node {node!r}")
        return f"{self.prefix}{node}"

    def exec(self, node: str, argv: List[str], stdin: Optional[str] = None,
             timeout: Optional[int] = None) -> ExecResult:
        cmd = ["docker", "exec"] + (["-i"] if stdin is not None else []) + [self.container(node)] + argv
        # stdin goes in as bytes: text mode on Windows would turn "\n" into "\r\n",
        # which iptables-restore inside the Linux container rejects.
        try:
            p = subprocess.run(cmd, input=stdin.encode() if stdin is not None else None,
                               capture_output=True, timeout=timeout or self.timeout)
        except subprocess.TimeoutExpired:
            return ExecResult(124, "", f"timeout after {timeout or self.timeout}s")
        out = p.stdout.decode(errors="replace")
        err = p.stderr.decode(errors="replace")
        if p.returncode != 0 and ("No such container" in err or "is not running" in err):
            raise LabError(err.strip())
        return ExecResult(p.returncode, out, err)

    def must(self, node: str, argv: List[str], stdin: Optional[str] = None) -> str:
        r = self.exec(node, argv, stdin=stdin)
        if not r.ok:
            raise LabError(f"{node}: {' '.join(argv)} failed: {r.text()}")
        return r.out

    def _json(self, node: str, argv: List[str]):
        out = self.must(node, argv).strip()
        return json.loads(out) if out else []

    # ---- interfaces -------------------------------------------------------
    def iface_map(self, node: str, refresh: bool = False) -> Dict[str, str]:
        """network name -> interface name inside the container, matched by MAC address."""
        if node in self._ifmap and not refresh:
            return self._ifmap[node]
        p = subprocess.run(
            ["docker", "inspect", "-f", "{{json .NetworkSettings.Networks}}", self.container(node)],
            capture_output=True, text=True, timeout=self.timeout,
        )
        if p.returncode != 0:
            raise LabError(f"docker inspect {node} failed: {p.stderr.strip()}")
        nets = json.loads(p.stdout)
        links = self._json(node, ["ip", "-j", "link", "show"])
        by_mac = {l.get("address", "").lower(): l["ifname"] for l in links}
        addrs = self._json(node, ["ip", "-j", "-4", "addr", "show"])
        by_ip = {a["local"]: l["ifname"] for l in addrs for a in l.get("addr_info", [])}
        mapping: Dict[str, str] = {}
        for net, ip in self.topo.nodes[node].interfaces.items():
            dname = self.topo.networks[net]["docker_name"]
            info = nets.get(dname, {})
            ifname = by_mac.get((info.get("MacAddress") or "").lower()) or by_ip.get(ip)
            if not ifname:
                raise LabError(f"{node}: cannot find interface for network {net}")
            mapping[net] = ifname
        self._ifmap[node] = mapping
        return mapping

    def ifaces(self, node: str) -> List[str]:
        return list(self.iface_map(node).values())

    def resolve_placeholders(self, node: str, cmd: str) -> str:
        """Replaces {if:<network>} with the real interface name on that node."""
        for net, ifname in self.iface_map(node).items():
            cmd = cmd.replace("{if:" + net + "}", ifname)
        return cmd

    # ---- state ------------------------------------------------------------
    def link_states(self, node: str) -> Dict[str, bool]:
        links = self._json(node, ["ip", "-j", "link", "show"])
        return {l["ifname"]: "UP" in l.get("flags", []) for l in links if l["ifname"] != "lo"}

    def mtus(self, node: str) -> Dict[str, int]:
        links = self._json(node, ["ip", "-j", "link", "show"])
        return {l["ifname"]: int(l.get("mtu", 0)) for l in links if l["ifname"] != "lo"}

    def addresses(self, node: str) -> Dict[str, List[str]]:
        data = self._json(node, ["ip", "-j", "-4", "addr", "show"])
        out: Dict[str, List[str]] = {}
        for l in data:
            if l["ifname"] == "lo":
                continue
            out[l["ifname"]] = sorted(f"{a['local']}/{a['prefixlen']}" for a in l.get("addr_info", []))
        return out

    def routes(self, node: str) -> List[dict]:
        """Non-kernel routes in the main table as {dst, gateway, dev}."""
        data = self._json(node, ["ip", "-j", "route", "show"])
        out = []
        for r in data:
            if r.get("protocol") == "kernel":
                continue
            out.append({"dst": r.get("dst", "default"), "gateway": r.get("gateway"), "dev": r.get("dev")})
        return sorted(out, key=lambda r: (r["dst"], r["gateway"] or "", r["dev"] or ""))

    def snapshot(self, node: str) -> dict:
        return {
            "links": self.link_states(node),
            "mtus": self.mtus(node),
            "addrs": self.addresses(node),
            "routes": self.routes(node),
            "iptables": self.must(node, ["iptables-save"]),
        }

    @staticmethod
    def snapshots_equal(a: dict, b: dict) -> bool:
        return (
            a["links"] == b["links"]
            and a.get("mtus") == b.get("mtus")
            and a["addrs"] == b["addrs"]
            and a["routes"] == b["routes"]
            and normalize_iptables(a["iptables"]) == normalize_iptables(b["iptables"])
        )

    def restore(self, node: str, snap: dict) -> List[str]:
        """Puts a node back to a snapshot. Returns a list of error messages (empty if clean)."""
        errors: List[str] = []

        def run(argv: List[str], stdin: Optional[str] = None) -> None:
            r = self.exec(node, argv, stdin=stdin)
            if not r.ok:
                errors.append(f"{' '.join(argv)}: {r.text()}")

        for ifname, mtu in snap.get("mtus", {}).items():
            run(["ip", "link", "set", ifname, "mtu", str(mtu)])
        for ifname, up in snap["links"].items():
            run(["ip", "link", "set", ifname, "up" if up else "down"])
        current = self.addresses(node)
        for ifname, addrs in snap["addrs"].items():
            if current.get(ifname, []) != addrs:
                run(["ip", "addr", "flush", "dev", ifname])
                for a in addrs:
                    run(["ip", "addr", "add", a, "dev", ifname])
        for r in self.routes(node):
            self.exec(node, ["ip", "route", "del"] + _route_args(r))
        for r in snap["routes"]:
            run(["ip", "route", "replace"] + _route_args(r))
        run(["iptables-restore"], stdin=snap["iptables"])
        self.exec(node, ["conntrack", "-F"])
        return errors

    # ---- provisioning -----------------------------------------------------
    def _iptables_baseline(self, node: str) -> str:
        spec = self.topo.nodes[node]
        policy = spec.forward_policy if spec.is_router else "ACCEPT"
        rules = "\n".join(spec.firewall)
        return f"*filter\n:INPUT ACCEPT [0:0]\n:FORWARD {policy} [0:0]\n:OUTPUT ACCEPT [0:0]\n{rules}\nCOMMIT\n"

    def provision(self, node: str) -> None:
        """Puts one node into its baseline state from topology.yaml. Idempotent."""
        spec = self.topo.nodes[node]
        ifmap = self.iface_map(node)
        for net, ifname in ifmap.items():
            self.must(node, ["ip", "link", "set", ifname, "mtu", str(self.topo.mtu(net)), "up"])
        current = self.addresses(node)
        for net, ip in spec.interfaces.items():
            ifname = ifmap[net]
            want = [f"{ip}/{self.topo.prefixlen(net)}"]
            if current.get(ifname, []) != want:
                self.exec(node, ["ip", "addr", "flush", "dev", ifname])
                self.must(node, ["ip", "addr", "add", want[0], "dev", ifname])
        for r in self.routes(node):
            self.exec(node, ["ip", "route", "del"] + _route_args(r))
        if spec.is_router:
            for r in spec.routes:
                self.must(node, ["ip", "route", "replace", r["prefix"], "via", r["via"]])
        elif spec.gateway:
            self.must(node, ["ip", "route", "replace", "default", "via", spec.gateway])
        self.must(node, ["iptables-restore"], stdin=self._iptables_baseline(node))
        self.exec(node, ["conntrack", "-F"])
        self.exec(node, ["ip", "route", "flush", "cache"])  # forget learned path MTUs between scenarios

    def provision_all(self) -> None:
        with ThreadPoolExecutor(max_workers=len(self.topo.nodes)) as pool:
            list(pool.map(self.provision, list(self.topo.nodes)))

    def reset(self) -> None:
        self.provision_all()

    # ---- flow tests -------------------------------------------------------
    def run_flow(self, flow: Flow) -> bool:
        dst_ip = self.topo.resolve(flow.dst)
        if flow.proto == "icmp":
            r = self.exec(flow.src, ["ping", "-c", "1", "-W", "1", dst_ip], timeout=8)
        elif flow.proto == "tcp":
            r = self.exec(flow.src, ["nc", "-z", "-w", "2", dst_ip, str(flow.port)], timeout=8)
        elif flow.proto == "tcp-bulk":
            r = self.exec(flow.src, ["python3", "/opt/np/bulk.py", dst_ip, str(flow.port), "65536", "3"],
                          timeout=10)
        else:
            raise LabError(f"unsupported proto {flow.proto}")
        return r.ok

    def run_command(self, node: str, cmd: str) -> ExecResult:
        """Runs one already-gated command string as an argument list (no shell)."""
        return self.exec(node, shlex.split(cmd))
