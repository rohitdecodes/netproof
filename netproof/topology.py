"""Loads lab/topology.yaml and answers questions about it (addresses, paths, scope)."""
from __future__ import annotations

import ipaddress
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

import yaml

from .config import LAB_DIR


@dataclass
class Node:
    name: str
    role: str                       # "host" or "router"
    interfaces: Dict[str, str]      # network name -> IPv4 address
    gateway: Optional[str] = None   # hosts only
    routes: List[dict] = field(default_factory=list)      # routers: [{prefix, via}]
    forward_policy: str = "ACCEPT"
    firewall: List[str] = field(default_factory=list)     # iptables -S style rules

    @property
    def is_router(self) -> bool:
        return self.role == "router"


@dataclass
class Topology:
    name: str
    networks: Dict[str, dict]
    nodes: Dict[str, Node]
    listen_ports: List[int]
    default_mtu: int = 1500

    # ---- addressing -------------------------------------------------------
    def mtu(self, network: str) -> int:
        return int(self.networks[network].get("mtu", self.default_mtu))

    def prefixlen(self, network: str) -> int:
        return ipaddress.ip_network(self.networks[network]["subnet"]).prefixlen

    def ip_of(self, name: str) -> str:
        """Primary address of a node: its first listed interface."""
        return next(iter(self.nodes[name].interfaces.values()))

    def resolve(self, name_or_ip: str) -> str:
        """Accepts a node name or an IPv4 address and returns an IPv4 address."""
        if name_or_ip in self.nodes:
            return self.ip_of(name_or_ip)
        ipaddress.ip_address(name_or_ip)  # raises ValueError if not an IP
        return name_or_ip

    def node_ips(self) -> Set[str]:
        return {ip for n in self.nodes.values() for ip in n.interfaces.values()}

    def routers(self) -> List[str]:
        return [n for n, node in self.nodes.items() if node.is_router]

    def network_members(self, network: str) -> List[str]:
        return [n for n, node in self.nodes.items() if network in node.interfaces]

    def neighbors(self, name: str) -> Set[str]:
        out: Set[str] = set()
        for net in self.nodes[name].interfaces:
            out.update(m for m in self.network_members(net) if m != name)
        return out

    # ---- paths and scope --------------------------------------------------
    def _distances(self, start: str, goal: str) -> Dict[str, int]:
        """BFS where only routers forward traffic (hosts are endpoints)."""
        dist = {start: 0}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur != start and cur != goal and not self.nodes[cur].is_router:
                continue
            for nb in self.neighbors(cur):
                if nb not in dist:
                    dist[nb] = dist[cur] + 1
                    q.append(nb)
        return dist

    def path_nodes(self, src: str, dst: str) -> Set[str]:
        """All nodes on any shortest forwarding path between src and dst, inclusive."""
        ds = self._distances(src, dst)
        dd = self._distances(dst, src)
        if dst not in ds:
            return {src, dst}
        total = ds[dst]
        return {n for n in self.nodes if n in ds and n in dd and ds[n] + dd[n] == total}

    def summary_lines(self) -> List[str]:
        lines = []
        for name, node in self.nodes.items():
            addrs = ", ".join(
                f"{ip}/{self.prefixlen(net)} on the {net} network" for net, ip in node.interfaces.items()
            )
            lines.append(f"- {name} ({node.role}): {addrs}")
        return lines


def load_topology(path: Optional[Path] = None) -> Topology:
    data = yaml.safe_load(Path(path or LAB_DIR / "topology.yaml").read_text())
    nodes = {
        name: Node(
            name=name,
            role=spec["role"],
            interfaces=dict(spec["interfaces"]),
            gateway=spec.get("gateway"),
            routes=list(spec.get("routes", [])),
            forward_policy=spec.get("forward_policy", "ACCEPT"),
            firewall=list(spec.get("firewall", [])),
        )
        for name, spec in data["nodes"].items()
    }
    return Topology(
        name=data["name"],
        networks=dict(data["networks"]),
        nodes=nodes,
        listen_ports=list(data.get("listen_ports", [])),
        default_mtu=int(data.get("default_mtu", 1500)),
    )
