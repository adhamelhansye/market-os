"""Pydantic v2 schemas for the creative learning API (Phase 8D).

Envelopes are explicit; engine evidence blocks remain versioned
structured payloads (each stamps its own rules_version).
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LearningGenerateResponse(BaseModel):
    business_id: str
    snapshot_id: UUID | None = None
    created: bool
    report: dict[str, Any]


class LearningSummaryResponse(BaseModel):
    status: str
    reason: str | None = None
    entities_total: int | None = None
    entities_sufficient: int | None = None
    patterns_total: int | None = None
    patterns_by_status: dict[str, int] | None = None
    learnings_total: int | None = None
    recommendations_total: int | None = None
    learning_status: str | None = None
    fingerprint: str | None = None
    rules_version: str | None = None
    range: dict[str, Any] | None = None


class LearningProjectionResponse(BaseModel):
    """Generic projection envelope for patterns/learnings/recommendations."""

    status: str
    reason: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class LearningSnapshotSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    range_kind: str
    start_date: date
    end_date: date
    currency: str
    rules_version: str
    fingerprint: str
    created_at: datetime


class LearningSnapshotRead(LearningSnapshotSummaryRead):
    payload: dict[str, Any]
