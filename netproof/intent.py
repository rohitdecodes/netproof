"""Intent spec (which flows must work and which must stay blocked) and the verifier logic."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol

import yaml

from .config import LAB_DIR


@dataclass(frozen=True)
class Flow:
    id: str
    src: str
    dst: str
    proto: str               # "tcp" or "icmp"
    port: Optional[int]
    expect: str              # "allow" or "deny"

    @property
    def wants_reachable(self) -> bool:
        return self.expect == "allow"

    def describe(self) -> str:
        port = f"/{self.port}" if self.port else ""
        return f"{self.src} -> {self.dst} {self.proto}{port}"


@dataclass(frozen=True)
class FlowResult:
    flow: Flow
    reachable: bool

    @property
    def ok(self) -> bool:
        return self.reachable == self.flow.wants_reachable


Results = Dict[str, FlowResult]


class FlowRunner(Protocol):
    def run_flow(self, flow: Flow) -> bool: ...


def load_intent(path: Optional[Path] = None) -> List[Flow]:
    data = yaml.safe_load(Path(path or LAB_DIR / "intent.yaml").read_text())
    flows = [
        Flow(
            id=f["id"],
            src=f["src"],
            dst=f["dst"],
            proto=f["proto"],
            port=f.get("port"),
            expect=f["expect"],
        )
        for f in data["flows"]
    ]
    ids = [f.id for f in flows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate flow ids in intent spec")
    return flows


def evaluate(lab: FlowRunner, flows: List[Flow], max_workers: int = 12) -> Results:
    """Runs every flow test in parallel and returns results keyed by flow id."""
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        reach = list(pool.map(lab.run_flow, flows))
    return {f.id: FlowResult(f, r) for f, r in zip(flows, reach)}


def matching_ids(results: Results) -> set:
    return {fid for fid, r in results.items() if r.ok}


def failing(results: Results) -> List[FlowResult]:
    return [r for r in results.values() if not r.ok]


def is_healthy(results: Results) -> bool:
    return all(r.ok for r in results.values())


@dataclass
class Comparison:
    regressions: List[str]    # matched intent before, not after
    improvements: List[str]   # did not match before, match after

    @property
    def has_regressions(self) -> bool:
        return bool(self.regressions)


def compare(before: Results, after: Results) -> Comparison:
    b, a = matching_ids(before), matching_ids(after)
    return Comparison(regressions=sorted(b - a), improvements=sorted(a - b))


def format_table(results: Results) -> str:
    lines = [f"{'flow':<18} {'path':<32} {'expect':<6} {'observed':<11} ok"]
    for r in results.values():
        observed = "reachable" if r.reachable else "blocked"
        lines.append(
            f"{r.flow.id:<18} {r.flow.describe():<32} {r.flow.expect:<6} {observed:<11} {'yes' if r.ok else 'NO'}"
        )
    return "\n".join(lines)
