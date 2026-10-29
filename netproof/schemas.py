"""Typed models for what the agent submits."""
from __future__ import annotations

from typing import List

from pydantic import BaseModel, Field

from .faults import ROOT_CAUSE_CLASSES

FAULT_CLASS_CHOICES = ROOT_CAUSE_CLASSES + ["other"]


class ChangePlan(BaseModel):
    device: str
    commands: List[str] = Field(min_length=1)
    rationale: str
    expected_effect: str
    rollback: List[str] = Field(default_factory=list)
    blast_radius: str = ""


class RootCause(BaseModel):
    device: str
    fault_class: str
    summary: str
