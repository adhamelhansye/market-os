"""Pydantic v2 schemas for the creative performance API (Phase 8C).

Envelopes are explicitly typed; engine evidence blocks are carried as
versioned structured payloads (each block stamps its own rules_version).
Decimals serialize as strings via the app-level encoder.
"""

from datetime import date, datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PerformanceLinkCreate(BaseModel):
    """Explicit attribution mapping authored by a user."""

    label: str | None = Field(default=None, max_length=200)
    creative_concept_id: UUID | None = None
    creative_test_variant_id: UUID | None = None
    ad_id: UUID | None = None
    provider_creative_id: UUID | None = None


class PerformanceLinkRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    business_id: UUID
    creative_concept_id: UUID | None = None
    creative_test_variant_id: UUID | None = None
    ad_id: UUID | None = None
    provider_creative_id: UUID | None = None
    label: str | None = None
    status: str
    created_at: datetime


class PerformanceReportResponse(BaseModel):
    business_id: str
    currency: str
    range: dict[str, Any]
    rules_versions: dict[str, str | None]
    break_even_roas_available: bool
    attribution: dict[str, Any]
    entities: list[dict[str, Any]]
    comparisons: dict[str, Any]
    fingerprint: str


class EntityPerformanceResponse(BaseModel):
    """One entity's performance; ``attribution`` carries the unavailable
    reason when no link exists, otherwise ``result`` holds the payload."""

    business_id: str
    range: dict[str, Any]
    attribution: dict[str, Any] | None = None
    result: dict[str, Any] | None = None


class SnapshotCreatedResponse(BaseModel):
    snapshot_id: UUID
    fingerprint: str
    created: bool


class SnapshotSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    range_kind: str
    start_date: date
    end_date: date
    currency: str
    entity_scope: str
    rules_version: str
    fingerprint: str
    created_at: datetime


class SnapshotRead(SnapshotSummaryRead):
    payload: dict[str, Any]
