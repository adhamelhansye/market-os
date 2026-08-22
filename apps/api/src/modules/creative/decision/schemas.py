"""Pydantic v2 schemas for the creative decision plan API (Phase 8F)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DecisionPlanGenerateResponse(BaseModel):
    business_id: str
    snapshot_id: UUID | None = None
    created: bool
    plan: dict[str, Any]


class ReviewStateUpdate(BaseModel):
    """Human review input. Records review state ONLY - nothing executes."""

    review_state: str = Field(
        description="One of: proposed, acknowledged, dismissed, deferred"
    )
    note: str | None = Field(default=None, max_length=500)


class ReviewStateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    opportunity_id: str
    source_plan_fingerprint: str
    review_state: str
    note: str | None = None
    decided_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class DecisionPlanSummaryResponse(BaseModel):
    status: str
    reason: str | None = None
    plan_status: str | None = None
    total_items: int | None = None
    blocked_count: int | None = None
    by_priority: dict[str, int] | None = None
    fingerprint: str | None = None
    rules_version: str | None = None
    source_optimization_fingerprint: str | None = None
    review_progress: dict[str, int] | None = None
    note: str | None = None


class DecisionItemsResponse(BaseModel):
    status: str
    reason: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class BlockedAppendixResponse(BaseModel):
    status: str
    reason: str | None = None
    actionable: bool = False
    items: list[dict[str, Any]] = Field(default_factory=list)


class DecisionSnapshotSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    rules_version: str
    fingerprint: str
    source_optimization_fingerprint: str | None = None
    created_at: datetime


class DecisionSnapshotRead(DecisionSnapshotSummaryRead):
    payload: dict[str, Any]
