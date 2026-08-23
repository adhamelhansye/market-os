"""Pydantic v2 schemas for the creative action preparation API (Phase 8G)."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class ActionGenerateResponse(BaseModel):
    business_id: str
    created_count: int
    report: dict[str, Any]


class ReviewStateUpdate(BaseModel):
    review_state: str = Field(
        description="One of: proposed, acknowledged, dismissed, deferred"
    )
    note: str | None = Field(default=None, max_length=500)


class ActionDraftRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    source_opportunity_id: str
    source_plan_fingerprint: str
    draft_test_id: str
    draft_kind: str
    review_state: str
    note: str | None = None
    decided_by: UUID | None = None
    created_at: datetime
    updated_at: datetime


class ActionItemsResponse(BaseModel):
    status: str
    reason: str | None = None
    drafts: list[dict[str, Any]] = Field(default_factory=list)
    skipped: list[dict[str, Any]] = Field(default_factory=list)
    excluded: list[dict[str, Any]] = Field(default_factory=list)
    orphaned: list[dict[str, Any]] = Field(default_factory=list)
