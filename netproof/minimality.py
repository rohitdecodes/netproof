"""Minimality: how far the final network state is from the known-good baseline.

A fix can make every flow pass and still leave junk behind (a faulty DROP rule shadowed
by a new ACCEPT, a wrong MTU, an extra route). residual items = differences between the
golden snapshot taken right after reset and the snapshot taken after the run.
A run is a "clean fix" when it is FIXED_VERIFIED and has zero residual items.
"""
from __future__ import annotations

import difflib
from typing import Dict, List

from .lab import normalize_iptables


def _route_key(r: dict) -> str:
    out = r.get("dst", "default")
    if r.get("gateway"):
        out += f" via {r['gateway']}"
    if r.get("dev"):
        out += f" dev {r['dev']}"
    return out


def snapshot_diff(golden: dict, final: dict) -> List[str]:
    items: List[str] = []
    for key, label in (("links", "link"), ("mtus", "mtu")):
        g, f = golden.get(key, {}), final.get(key, {})
        for ifname in sorted(set(g) | set(f)):
            if g.get(ifname) != f.get(ifname):
                items.append(f"{label} {ifname}: {g.get(ifname)} -> {f.get(ifname)}")
    ga, fa = golden.get("addrs", {}), final.get("addrs", {})
    for ifname in sorted(set(ga) | set(fa)):
        if ga.get(ifname, []) != fa.get(ifname, []):
            items.append(f"addr {ifname}: {ga.get(ifname, [])} -> {fa.get(ifname, [])}")
    gr = {_route_key(r) for r in golden.get("routes", [])}
    fr = {_route_key(r) for r in final.get("routes", [])}
    items += [f"route missing: {r}" for r in sorted(gr - fr)]
    items += [f"route extra: {r}" for r in sorted(fr - gr)]
    gi = normalize_iptables(golden.get("iptables", "")).splitlines()
    fi = normalize_iptables(final.get("iptables", "")).splitlines()
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(a=gi, b=fi, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            items += [f"rule missing: {line}" for line in gi[i1:i2]]
        if op in ("insert", "replace"):
            items += [f"rule extra: {line}" for line in fi[j1:j2]]
    return items


def residual(golden: Dict[str, dict], final: Dict[str, dict]) -> Dict[str, List[str]]:
    """Per-device residual items; devices with no differences are omitted."""
    out = {}
    for node in sorted(set(golden) | set(final)):
        diff = snapshot_diff(golden.get(node, {}), final.get(node, {}))
        if diff:
            out[node] = diff
    return out


def residual_count(res: Dict[str, List[str]]) -> int:
    return sum(len(v) for v in res.values())
