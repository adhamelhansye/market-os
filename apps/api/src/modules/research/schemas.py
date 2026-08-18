"""Research module schemas (Phase 6A).

Pydantic request/response contracts. Response models never expose
internal ORM models directly: they are explicit DTOs (ORM objects are
mapped via `from_attributes` only into response models that carry no
`organization_id`/`business_id` columns).

Classification inputs are validated deterministically server-side with
fixed vocabularies from `constants.py`. Money inside JSONB is stored as
Decimal-as-string (never float).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field

from src.modules.research.constants import (
    CLASSIFICATION_VALUES,
    CONFIDENCE_VALUES,
    EVIDENCE_TYPES,
    FINDING_CATEGORIES,
    IMPORTANCE_VALUES,
    PROJECT_STATUSES,
    PROVENANCE_VALUES,
    RESEARCH_TYPES,
    SOURCE_TYPES,
)
from src.modules.research.errors import (
    MAX_RAW_EXCERPT_LENGTH,
    ResearchClassificationError,
)


class ResearchProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    type: str
    status: str
    scope: str | None = None
    created_at: datetime
    updated_at: datetime


class ResearchProjectDetailResponse(ResearchProjectResponse):
    source_count: int = 0
    evidence_count: int = 0
    finding_count: int = 0
    competitor_count: int = 0
    data_quality: dict[str, Any] = Field(default_factory=dict)


class ResearchProjectListResponse(BaseModel):
    projects: list[ResearchProjectResponse]
    total: int


class ResearchCompetitorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    domain: str | None = None
    description: str | None = None
    market: str | None = None
    status: str
    metadata_json: dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    created_at: datetime
    updated_at: datetime


class ResearchCompetitorListResponse(BaseModel):
    competitors: list[ResearchCompetitorResponse]
    total: int


class ResearchSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_type: str
    title: str
    url: str | None = None
    original_url: str | None = None
    normalized_url: str | None = None
    domain: str | None = None
    author: str | None = None
    published_at: datetime | None = None
    captured_at: datetime
    content_hash: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")
    status: str
    competitor_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime


class ResearchSnapshotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    captured_at: datetime
    content_hash: str
    content: str
    metadata_json: dict[str, Any] = Field(default_factory=dict, serialization_alias="metadata")


class ResearchSourceDetailResponse(ResearchSourceResponse):
    snapshots: list[ResearchSnapshotResponse] = Field(default_factory=list)


class ResearchSourceListResponse(BaseModel):
    sources: list[ResearchSourceResponse]
    total: int


class ResearchEvidenceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    source_id: uuid.UUID
    research_project_id: uuid.UUID | None = None
    snapshot_id: uuid.UUID | None = None
    evidence_type: str
    statement: str
    raw_excerpt: str | None = None
    structured_value: dict[str, Any] | None = None
    unit: str | None = None
    captured_at: datetime
    classification: str
    provenance: str
    created_at: datetime
    updated_at: datetime


class ResearchEvidenceListResponse(BaseModel):
    evidence: list[ResearchEvidenceResponse]
    total: int


class ResearchFindingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_project_id: uuid.UUID
    category: str
    title: str
    statement: str
    classification: str
    importance: str
    evidence_strength: str
    created_at: datetime
    updated_at: datetime


class ResearchEvidenceSummary(BaseModel):
    id: uuid.UUID
    source_id: uuid.UUID
    evidence_type: str
    statement: str
    classification: str
    provenance: str
    raw_excerpt: str | None = None


class ResearchFindingDetailResponse(ResearchFindingResponse):
    evidence: list[ResearchEvidenceSummary] = Field(default_factory=list)


class ResearchFindingListResponse(BaseModel):
    findings: list[ResearchFindingResponse]
    total: int


class ResearchSearchHitResponse(BaseModel):
    entity_type: str
    entity_id: uuid.UUID
    title: str
    statement: str | None = None
    source_id: uuid.UUID | None = None
    source_title: str | None = None
    source_domain: str | None = None
    evidence_type: str | None = None
    classification: str | None = None
    captured_at: datetime | None = None


class ResearchSearchResponse(BaseModel):
    hits: list[ResearchSearchHitResponse]
    total: int


class ResearchCollectionJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    research_project_id: uuid.UUID
    source_id: uuid.UUID | None = None
    provider: str
    mode: str
    status: str
    max_pages: int
    max_depth: int
    same_domain: bool
    pages_collected: int
    change_status: str | None = None
    attempts: int
    error: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class ResearchCollectionJobListResponse(BaseModel):
    collections: list[ResearchCollectionJobResponse]
    total: int


class ResearchCollectionRequest(BaseModel):
    research_project_id: uuid.UUID | None = None
    source_url: str | None = Field(default=None, max_length=2048)
    mode: str = "single_page"
    max_pages: int = Field(default=1, ge=1, le=50)
    max_depth: int = Field(default=0, ge=0, le=2)
    same_domain: bool = True
    refresh: bool = False
    specific_urls: list[str] = Field(default_factory=list, max_length=50)
    idempotency_key: str | None = Field(default=None, max_length=255)


class ResearchCollectionCancelResponse(BaseModel):
    collection: ResearchCollectionJobResponse


# ---------------------------------------------------------------------------
# Create / update request models (explicit tenant-free DTOs)
# ---------------------------------------------------------------------------
class ResearchProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    type: str
    scope: str | None = Field(default=None, max_length=1000)


class ResearchProjectStatusRequest(BaseModel):
    status: str


class ResearchCompetitorCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    domain: str | None = Field(default=None, max_length=255)
    description: str | None = Field(default=None, max_length=5_000)
    market: str | None = Field(default=None, max_length=100)
    status: str = "active"
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchSourceCreateRequest(BaseModel):
    source_type: str
    title: str = Field(min_length=1, max_length=255)
    url: str | None = Field(default=None, max_length=1024)
    domain: str | None = Field(default=None, max_length=255)
    author: str | None = Field(default=None, max_length=255)
    published_at: datetime | None = None
    competitor_id: uuid.UUID | None = None

    # Captured content: literal text the client submits. The API never
    # fetches `url`; content drives the deduplication hash.
    content: str | None = Field(default=None, max_length=1_000_000)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ResearchEvidenceCreateRequest(BaseModel):
    source_id: uuid.UUID
    evidence_type: str
    statement: str = Field(min_length=1, max_length=50_000)
    raw_excerpt: str | None = Field(default=None, max_length=MAX_RAW_EXCERPT_LENGTH)
    structured_value: dict[str, Any] | None = None
    unit: str | None = Field(default=None, max_length=20)
    captured_at: datetime | None = None
    classification: str = Field(
        default="observed",
        validation_alias=AliasChoices("classification", "confidence"),
    )
    provenance: str = "collected"


class ResearchFindingCreateRequest(BaseModel):
    research_project_id: uuid.UUID
    category: str
    title: str = Field(min_length=1, max_length=255)
    statement: str = Field(min_length=1, max_length=50_000)
    classification: str | None = None
    importance: str = "medium"
    evidence_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)


# ---------------------------------------------------------------------------
# Deterministic vocabulary validation (validators raise
# ResearchClassificationError with a stable error code).
# ---------------------------------------------------------------------------
def _validate_in(field: str, value: str, allowed: frozenset[str]) -> str:
    if value not in allowed:
        raise ResearchClassificationError(field, value, allowed)
    return value


def validate_source_type(value: str) -> str:
    return _validate_in("source_type", value, SOURCE_TYPES)


def validate_evidence_type(value: str) -> str:
    return _validate_in("evidence_type", value, EVIDENCE_TYPES)


def validate_finding_category(value: str) -> str:
    return _validate_in("category", value, FINDING_CATEGORIES)


def validate_importance(value: str) -> str:
    return _validate_in("importance", value, IMPORTANCE_VALUES)


def validate_provenance(value: str) -> str:
    return _validate_in("provenance", value, PROVENANCE_VALUES)


def validate_classification(value: str) -> str:
    return _validate_in("classification", value, CLASSIFICATION_VALUES)


def validate_confidence(value: str) -> str:
    return _validate_in("confidence", value, CONFIDENCE_VALUES)


def validate_project_type(value: str) -> str:
    return _validate_in("type", value, RESEARCH_TYPES)


def validate_project_status(value: str) -> str:
    return _validate_in("status", value, PROJECT_STATUSES)
