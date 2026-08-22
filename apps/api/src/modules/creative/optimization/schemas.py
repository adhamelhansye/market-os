"""Pydantic v2 schemas for the creative optimization API (Phase 8E)."""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OptimizationGenerateResponse(BaseModel):
    business_id: str
    snapshot_id: UUID | None = None
    created: bool
    plan: dict[str, Any]


class OptimizationSummaryResponse(BaseModel):
    status: str
    reason: str | None = None
    optimization_status: str | None = None
    entities_total: int | None = None
    entities_sufficient: int | None = None
    opportunities_total: int | None = None
    blocked_total: int | None = None
    by_priority: dict[str, int] | None = None
    fingerprint: str | None = None
    rules_version: str | None = None
    note: str | None = None


class OptimizationProjectionResponse(BaseModel):
    status: str
    reason: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)


class OptimizationSectionResponse(BaseModel):
    status: str
    reason: str | None = None


class OptimizationSnapshotSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    range_kind: str
    start_date: date
    end_date: date
    currency: str
    rules_version: str
    fingerprint: str
    created_at: datetime


class OptimizationSnapshotRead(OptimizationSnapshotSummaryRead):
    payload: dict[str, Any]
