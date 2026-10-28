"""Executor: gate -> snapshot -> apply -> verify -> commit or roll back.

Commit rule: keep a change only if it causes zero regressions AND strictly increases
the number of flows that match intent. Otherwise restore the device snapshot.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional

from .gate import GateContext, check_plan
from .intent import Flow, Results, compare, evaluate, failing, is_healthy
from .schemas import ChangePlan


class PlanOutcome(str, Enum):
    COMMITTED = "COMMITTED"
    REJECTED_BY_GATE = "REJECTED_BY_GATE"
    ROLLED_BACK_COLLATERAL = "ROLLED_BACK_COLLATERAL"
    ROLLED_BACK_NO_EFFECT = "ROLLED_BACK_NO_EFFECT"


@dataclass
class PlanResult:
    outcome: PlanOutcome
    gate_violations: List[str] = field(default_factory=list)
    apply_errors: List[str] = field(default_factory=list)
    regressions: List[str] = field(default_factory=list)
    improvements: List[str] = field(default_factory=list)
    still_failing: List[str] = field(default_factory=list)
    healthy_after: bool = False
    restored_ok: Optional[bool] = None
    restore_errors: List[str] = field(default_factory=list)
    seconds: float = 0.0

    def to_dict(self) -> dict:
        d = self.__dict__.copy()
        d["outcome"] = self.outcome.value
        return d

    def feedback(self) -> str:
        """Plain-language result returned to the agent as the submit_plan tool output."""
        if self.outcome == PlanOutcome.REJECTED_BY_GATE:
            return ("REJECTED BY POLICY GATE. Nothing was changed. Violations:\n- "
                    + "\n- ".join(self.gate_violations))
        if self.outcome == PlanOutcome.ROLLED_BACK_COLLATERAL:
            return ("ROLLED BACK. The change broke flows that were working or correctly blocked: "
                    + ", ".join(self.regressions)
                    + ". The device was restored to its previous state.")
        if self.outcome == PlanOutcome.ROLLED_BACK_NO_EFFECT:
            msg = "ROLLED BACK. No flow improved."
            if self.apply_errors:
                msg += " Command errors: " + " | ".join(self.apply_errors)
            msg += " Still failing: " + ", ".join(self.still_failing) + ". The device was restored."
            return msg
        if self.healthy_after:
            return "COMMITTED. Every flow now matches the intent. The incident is resolved."
        return ("COMMITTED (partial). Improved: " + ", ".join(self.improvements)
                + ". Still failing: " + ", ".join(self.still_failing) + ". Continue investigating.")


class Executor:
    def __init__(self, lab, flows: List[Flow]):
        self.lab = lab
        self.flows = flows

    def _restore(self, device: str, snap: dict, result: PlanResult) -> None:
        result.restore_errors = self.lab.restore(device, snap)
        result.restored_ok = self.lab.snapshots_equal(self.lab.snapshot(device), snap)

    def execute(self, plan: ChangePlan, ctx: GateContext, before: Optional[Results] = None) -> PlanResult:
        t0 = time.monotonic()
        verdict = check_plan(plan, ctx)
        if not verdict.allowed:
            return PlanResult(PlanOutcome.REJECTED_BY_GATE, gate_violations=verdict.violations,
                              seconds=time.monotonic() - t0)
        before = before or evaluate(self.lab, self.flows)
        snap = self.lab.snapshot(plan.device)
        result = PlanResult(PlanOutcome.COMMITTED)

        for cmd in plan.commands:
            r = self.lab.run_command(plan.device, cmd)
            if not r.ok:
                result.apply_errors.append(f"{cmd!r}: {r.text() or 'exit ' + str(r.code)}")
                break

        after = evaluate(self.lab, self.flows)
        cmp = compare(before, after)
        result.regressions = cmp.regressions
        result.improvements = cmp.improvements
        result.still_failing = [r.flow.id for r in failing(after)]

        if cmp.has_regressions:
            result.outcome = PlanOutcome.ROLLED_BACK_COLLATERAL
            self._restore(plan.device, snap, result)
        elif result.apply_errors or not cmp.improvements:
            result.outcome = PlanOutcome.ROLLED_BACK_NO_EFFECT
            self._restore(plan.device, snap, result)
            result.still_failing = [r.flow.id for r in failing(before)]
        else:
            result.healthy_after = is_healthy(after)
        result.seconds = time.monotonic() - t0
        return result
