"""Research endpoints: deterministic storage for research intelligence.

Every route resolves `business_id` from the path via the central
`get_business_from_path` dependency (server-side tenancy validation, 404
on unknown businesses) and requires the `business:read` permission for
reads and `business:write` for writes.

The layer stores what clients submit; it never fetches URLs, never
scrapes, never calls LLMs and never takes autonomous action.

Resource ids are always resolved inside the authorized business —
unknown or cross-tenant ids return 404, never a leak.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import func, select

from src.core.dependencies import (
    CurrentBusinessId,
    CurrentUser,
    DbSession,
    require_permission,
)
from src.core.exceptions import ApiError, NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import (
    ResearchCollectionJob,
    ResearchCompetitor,
    ResearchEvidence,
    ResearchFinding,
    ResearchProject,
    ResearchSource,
)
from src.modules.businesses.service import get_business
from src.modules.research import intelligence as research_intelligence
from src.modules.research import service as research_service
from src.modules.research.collection import jobs as collection_jobs
from src.modules.research.collection import service as collection_service
from src.modules.research.collection.errors import CollectionRequestError
from src.modules.research.collection.provider import CollectionError
from src.modules.research.collection.security import URLPolicyError
from src.modules.research.schemas import (
    ResearchCollectionCancelResponse,
    ResearchCollectionJobListResponse,
    ResearchCollectionJobResponse,
    ResearchCollectionRequest,
    ResearchCompetitorCreateRequest,
    ResearchCompetitorListResponse,
    ResearchCompetitorResponse,
    ResearchEvidenceCreateRequest,
    ResearchEvidenceListResponse,
    ResearchEvidenceResponse,
    ResearchEvidenceSummary,
    ResearchFindingCreateRequest,
    ResearchFindingDetailResponse,
    ResearchFindingListResponse,
    ResearchFindingResponse,
    ResearchIntelligenceItemResponse,
    ResearchIntelligenceProvenanceResponse,
    ResearchIntelligenceResponse,
    ResearchIntelligenceSnapshotResponse,
    ResearchIntelligenceSummaryResponse,
    ResearchPricingResponse,
    ResearchProjectCreateRequest,
    ResearchProjectDetailResponse,
    ResearchProjectListResponse,
    ResearchProjectResponse,
    ResearchProjectStatusRequest,
    ResearchSearchResponse,
    ResearchSnapshotResponse,
    ResearchSourceCreateRequest,
    ResearchSourceDetailResponse,
    ResearchSourceListResponse,
    ResearchSourceResponse,
)

router = APIRouter(tags=["research"])

_PROJECT_ID = Path(description="Research project id.")
_COMPETITOR_ID = Path(description="Competitor id.")
_SOURCE_ID = Path(description="Research source id.")
_FINDING_ID = Path(description="Finding id.")


def _get_store(session: DbSession) -> research_service.ResearchStore:
    return research_service.ResearchStore(session)


def _not_found(entity: str, entity_id: uuid.UUID) -> NotFoundError:
    return NotFoundError(f"{entity} not found in this business", details={"id": str(entity_id)})


def _to_source_response(source: ResearchSource) -> ResearchSourceResponse:
    return ResearchSourceResponse.model_validate(source)


def _to_evidence_response(evidence: ResearchEvidence) -> ResearchEvidenceResponse:
    return ResearchEvidenceResponse.model_validate(evidence)


def _to_finding_response(finding: ResearchFinding) -> ResearchFindingResponse:
    return ResearchFindingResponse.model_validate(finding)


def _to_competitor_response(competitor: ResearchCompetitor) -> ResearchCompetitorResponse:
    return ResearchCompetitorResponse.model_validate(competitor)


def _to_project_response(project: ResearchProject) -> ResearchProjectResponse:
    return ResearchProjectResponse.model_validate(project)


async def _intelligence_response(
    session: DbSession,
    business,
    *,
    intelligence_type: str,
    project_id: uuid.UUID | None = None,
    competitor_id: uuid.UUID | None = None,
    category: str | None = None,
    classification: str | None = None,
    strength: str | None = None,
    freshness: str | None = None,
    source_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 100,
) -> ResearchIntelligenceResponse:
    store = research_intelligence.ResearchIntelligenceStore(session)
    snapshot = await store.ensure_snapshot(business, project_id)
    items = await store.items(
        business,
        snapshot,
        intelligence_type=intelligence_type,
        project_id=project_id,
        competitor_id=competitor_id,
        category=category,
        classification=classification,
        strength=strength,
        freshness_value=freshness,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )
    responses = []
    for item in items:
        response = ResearchIntelligenceItemResponse.model_validate(item)
        response.provenance = [
            ResearchIntelligenceProvenanceResponse(**row)
            for row in await store.provenance(business, item)
        ]
        responses.append(response)
    return ResearchIntelligenceResponse(
        snapshot_id=snapshot.id,
        intelligence_type=intelligence_type,
        generated_at=snapshot.generated_at,
        intelligence_version=snapshot.intelligence_version,
        items=responses,
        total=len(responses),
        freshness=snapshot.freshness,
        coverage=snapshot.coverage_json,
        missing_research_areas=snapshot.missing_areas_json,
    )


async def _get_project_or_404(
    session: DbSession, business, project_id: uuid.UUID
) -> ResearchProject:
    project = await _get_store(session).get_project(business, project_id)
    if project is None:
        raise _not_found("research project", project_id)
    return project


# ---------------------------------------------------------------------------
# Research projects
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/projects",
    response_model=ResearchProjectListResponse,
    summary="List research projects",
)
async def research_project_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchProjectListResponse:
    business = await get_business(session, business_id)
    projects, total = await _get_store(session).list_projects(business, limit=limit)
    return ResearchProjectListResponse(
        projects=[_to_project_response(p) for p in projects], total=total
    )


@router.post(
    "/businesses/{business_id}/research/projects",
    response_model=ResearchProjectResponse,
    status_code=201,
    summary="Create a research project",
)
async def research_project_create(
    payload: ResearchProjectCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
) -> ResearchProjectResponse:
    business = await get_business(session, business_id)
    project = await _get_store(session).create_project(
        business, request=payload, created_by=user.id
    )
    return _to_project_response(project)


@router.get(
    "/businesses/{business_id}/research/projects/{project_id}",
    response_model=ResearchProjectDetailResponse,
    summary="Get a research project with data-quality summary",
)
async def research_project_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    project_id: uuid.UUID = _PROJECT_ID,
) -> ResearchProjectDetailResponse:
    business = await get_business(session, business_id)
    project = await _get_project_or_404(session, business, project_id)
    summary = await _get_store(session).project_summary(business, project.id)
    response = ResearchProjectDetailResponse.model_validate(project)
    response.source_count = int(summary.get("source_count", 0))
    response.evidence_count = int(summary.get("evidence_count", 0))
    response.finding_count = int(summary.get("finding_count", 0))
    response.competitor_count = int(summary.get("competitor_count", 0))
    response.data_quality = summary
    return response


@router.patch(
    "/businesses/{business_id}/research/projects/{project_id}/status",
    response_model=ResearchProjectResponse,
    summary="Update research project status",
)
async def research_project_status(
    payload: ResearchProjectStatusRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    project_id: uuid.UUID = _PROJECT_ID,
) -> ResearchProjectResponse:
    business = await get_business(session, business_id)
    project = await _get_project_or_404(session, business, project_id)
    updated = await _get_store(session).set_project_status(business, project, request=payload)
    return _to_project_response(updated)


# ---------------------------------------------------------------------------
# Competitors
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/competitors",
    response_model=ResearchCompetitorListResponse,
    summary="List competitors",
)
async def research_competitor_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchCompetitorListResponse:
    business = await get_business(session, business_id)
    competitors, total = await _get_store(session).list_competitors(business, limit=limit)
    return ResearchCompetitorListResponse(
        competitors=[_to_competitor_response(c) for c in competitors], total=total
    )


@router.post(
    "/businesses/{business_id}/research/competitors",
    response_model=ResearchCompetitorResponse,
    status_code=201,
    summary="Create a competitor",
)
async def research_competitor_create(
    payload: ResearchCompetitorCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
) -> ResearchCompetitorResponse:
    business = await get_business(session, business_id)
    competitor = await _get_store(session).create_competitor(
        business, request=payload, created_by=user.id
    )
    return _to_competitor_response(competitor)


@router.get(
    "/businesses/{business_id}/research/competitors/{competitor_id}",
    response_model=ResearchCompetitorResponse,
    summary="Get one competitor",
)
async def research_competitor_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    competitor_id: uuid.UUID = _COMPETITOR_ID,
) -> ResearchCompetitorResponse:
    business = await get_business(session, business_id)
    competitor = await _get_store(session).get_competitor(business, competitor_id)
    if competitor is None:
        raise _not_found("competitor", competitor_id)
    return _to_competitor_response(competitor)


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/sources",
    response_model=ResearchSourceListResponse,
    summary="List research sources",
)
async def research_source_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    source_type: Annotated[str | None, Query()] = None,
    competitor_id: Annotated[uuid.UUID | None, Query()] = None,
    status: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchSourceListResponse:
    business = await get_business(session, business_id)
    sources, total = await _get_store(session).list_sources(
        business,
        source_type=source_type,
        competitor_id=competitor_id,
        status=status,
        limit=limit,
    )
    return ResearchSourceListResponse(
        sources=[_to_source_response(s) for s in sources], total=total
    )


@router.post(
    "/businesses/{business_id}/research/sources",
    response_model=ResearchSourceResponse,
    status_code=201,
    summary="Create a research source (deduplicated by content hash)",
)
async def research_source_create(
    payload: ResearchSourceCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
) -> ResearchSourceResponse:
    business = await get_business(session, business_id)
    source = await _get_store(session).create_source(business, request=payload, created_by=user.id)
    return _to_source_response(source)


@router.get(
    "/businesses/{business_id}/research/sources/{source_id}",
    response_model=ResearchSourceDetailResponse,
    summary="Get a research source with its snapshots",
)
async def research_source_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    source_id: uuid.UUID = _SOURCE_ID,
) -> ResearchSourceDetailResponse:
    business = await get_business(session, business_id)
    source = await _get_store(session).get_source(business, source_id)
    if source is None:
        raise _not_found("research source", source_id)
    snapshots = await _get_store(session).get_source_snapshots(source)
    response = ResearchSourceDetailResponse.model_validate(source)
    response.snapshots = [ResearchSnapshotResponse.model_validate(s) for s in snapshots]
    return response


# ---------------------------------------------------------------------------
# Evidence
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/search",
    response_model=ResearchSearchResponse,
    summary="Search research content across evidence, sources, findings and competitors",
)
async def research_evidence_search(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    q: Annotated[str, Query(min_length=1, max_length=200, description="Search text.")],
    limit: Annotated[int, Query(ge=1, le=200)] = 20,
) -> ResearchSearchResponse:
    business = await get_business(session, business_id)
    rows = await _get_store(session).search_research(business, q, limit=limit)
    return ResearchSearchResponse(hits=rows, total=len(rows))


@router.get(
    "/businesses/{business_id}/research/evidence",
    response_model=ResearchEvidenceListResponse,
    summary="List evidence",
)
async def research_evidence_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    evidence_type: Annotated[str | None, Query()] = None,
    source_id: Annotated[uuid.UUID | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    confidence: Annotated[str | None, Query()] = None,
    provenance: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchEvidenceListResponse:
    business = await get_business(session, business_id)
    evidence, total = await _get_store(session).list_evidence(
        business,
        evidence_type=evidence_type,
        source_id=source_id,
        classification=classification,
        confidence=confidence,
        provenance=provenance,
        limit=limit,
    )
    return ResearchEvidenceListResponse(
        evidence=[_to_evidence_response(e) for e in evidence], total=total
    )


@router.post(
    "/businesses/{business_id}/research/evidence",
    response_model=ResearchEvidenceResponse,
    status_code=201,
    summary="Create evidence from an existing source",
)
async def research_evidence_create(
    payload: ResearchEvidenceCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
) -> ResearchEvidenceResponse:
    business = await get_business(session, business_id)
    evidence = await _get_store(session).create_evidence(
        business, request=payload, created_by=user.id
    )
    return _to_evidence_response(evidence)


# ---------------------------------------------------------------------------
# Findings
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/findings",
    response_model=ResearchFindingListResponse,
    summary="List findings",
)
async def research_finding_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    importance: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchFindingListResponse:
    business = await get_business(session, business_id)
    findings, total = await _get_store(session).list_findings(
        business,
        research_project_id=research_project_id,
        category=category,
        classification=classification,
        importance=importance,
        limit=limit,
    )
    return ResearchFindingListResponse(
        findings=[_to_finding_response(f) for f in findings], total=total
    )


@router.post(
    "/businesses/{business_id}/research/findings",
    response_model=ResearchFindingResponse,
    status_code=201,
    summary="Create a finding linked to evidence",
)
async def research_finding_create(
    payload: ResearchFindingCreateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
) -> ResearchFindingResponse:
    business = await get_business(session, business_id)
    finding = await _get_store(session).create_finding(
        business, request=payload, created_by=user.id
    )
    return _to_finding_response(finding)


@router.get(
    "/businesses/{business_id}/research/findings/{finding_id}",
    response_model=ResearchFindingDetailResponse,
    summary="Get a finding with its evidence chain",
)
async def research_finding_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    finding_id: uuid.UUID = _FINDING_ID,
) -> ResearchFindingDetailResponse:
    business = await get_business(session, business_id)
    result = await _get_store(session).get_finding(business, finding_id)
    if result is None:
        raise _not_found("finding", finding_id)
    finding, evidence = result
    response = ResearchFindingDetailResponse.model_validate(finding)
    response.evidence = [
        ResearchEvidenceSummary(
            id=e.id,
            source_id=e.source_id,
            evidence_type=e.evidence_type,
            statement=e.statement,
            classification=e.classification,
            provenance=e.provenance,
            raw_excerpt=e.raw_excerpt,
        )
        for e in evidence
    ]
    return response


# ---------------------------------------------------------------------------
# Deterministic research intelligence
# ---------------------------------------------------------------------------
@router.get(
    "/businesses/{business_id}/research/intelligence/market",
    response_model=ResearchIntelligenceResponse,
    summary="Get deterministic market intelligence",
)
async def research_intelligence_market(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    freshness: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchIntelligenceResponse:
    business = await get_business(session, business_id)
    return await _intelligence_response(
        session,
        business,
        intelligence_type="market",
        project_id=research_project_id,
        category=category,
        classification=classification,
        strength=strength,
        freshness=freshness,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/customer",
    response_model=ResearchIntelligenceResponse,
    summary="Get deterministic customer intelligence",
)
async def research_intelligence_customer(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    freshness: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchIntelligenceResponse:
    business = await get_business(session, business_id)
    return await _intelligence_response(
        session,
        business,
        intelligence_type="customer",
        project_id=research_project_id,
        category=category,
        classification=classification,
        strength=strength,
        freshness=freshness,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/competitors",
    response_model=ResearchIntelligenceResponse,
    summary="Get deterministic competitor intelligence",
)
async def research_intelligence_competitors(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    competitor_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    freshness: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    date_from: Annotated[datetime | None, Query()] = None,
    date_to: Annotated[datetime | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchIntelligenceResponse:
    business = await get_business(session, business_id)
    if competitor_id is not None:
        competitor = await session.scalar(
            select(ResearchCompetitor).where(
                ResearchCompetitor.id == competitor_id,
                ResearchCompetitor.organization_id == business.organization_id,
                ResearchCompetitor.business_id == business.id,
            )
        )
        if competitor is None:
            raise _not_found("competitor", competitor_id)
    return await _intelligence_response(
        session,
        business,
        intelligence_type="competitor",
        project_id=research_project_id,
        competitor_id=competitor_id,
        category=category,
        classification=classification,
        strength=strength,
        freshness=freshness,
        source_type=source_type,
        date_from=date_from,
        date_to=date_to,
        limit=limit,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/competitors/{competitor_id}",
    response_model=ResearchIntelligenceResponse,
    summary="Get one competitor's intelligence",
)
async def research_intelligence_competitor(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    competitor_id: uuid.UUID,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    category: Annotated[str | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    freshness: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchIntelligenceResponse:
    business = await get_business(session, business_id)
    competitor = await session.scalar(
        select(ResearchCompetitor).where(
            ResearchCompetitor.id == competitor_id,
            ResearchCompetitor.organization_id == business.organization_id,
            ResearchCompetitor.business_id == business.id,
        )
    )
    if competitor is None:
        raise _not_found("competitor", competitor_id)
    return await _intelligence_response(
        session,
        business,
        intelligence_type="competitor",
        project_id=research_project_id,
        competitor_id=competitor_id,
        category=category,
        classification=classification,
        strength=strength,
        freshness=freshness,
        limit=limit,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/pricing",
    response_model=ResearchPricingResponse,
    summary="Get deterministic pricing intelligence",
)
async def research_intelligence_pricing(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    competitor_id: Annotated[uuid.UUID | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchPricingResponse:
    business = await get_business(session, business_id)
    base = await _intelligence_response(
        session,
        business,
        intelligence_type="competitor" if competitor_id else "market",
        project_id=research_project_id,
        competitor_id=competitor_id,
        category="pricing",
        classification=classification,
        strength=strength,
        limit=limit,
    )
    pricing = await research_intelligence.ResearchIntelligenceStore(session).pricing_summary(
        business, research_project_id, competitor_id
    )
    return ResearchPricingResponse(**base.model_dump(), pricing=pricing)


@router.get(
    "/businesses/{business_id}/research/intelligence/messaging",
    response_model=ResearchIntelligenceResponse,
    summary="Get observed messaging patterns",
)
async def research_intelligence_messaging(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
    classification: Annotated[str | None, Query()] = None,
    strength: Annotated[str | None, Query()] = None,
    freshness: Annotated[str | None, Query()] = None,
    source_type: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchIntelligenceResponse:
    business = await get_business(session, business_id)
    return await _intelligence_response(
        session,
        business,
        intelligence_type="market",
        project_id=research_project_id,
        category="messaging",
        classification=classification,
        strength=strength,
        freshness=freshness,
        source_type=source_type,
        limit=limit,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/summary",
    response_model=ResearchIntelligenceSummaryResponse,
    summary="Get deterministic research intelligence summary",
)
async def research_intelligence_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ResearchIntelligenceSummaryResponse:
    business = await get_business(session, business_id)
    store = research_intelligence.ResearchIntelligenceStore(session)
    snapshot = await store.ensure_snapshot(business, research_project_id)
    counts = {}
    for intelligence_type in ("market", "customer", "competitor"):
        counts[intelligence_type] = len(
            await store.items(business, snapshot, intelligence_type=intelligence_type, limit=200)
        )
    competitor_count = int(
        await session.scalar(
            select(func.count())
            .select_from(ResearchCompetitor)
            .where(
                ResearchCompetitor.organization_id == business.organization_id,
                ResearchCompetitor.business_id == business.id,
            )
        )
        or 0
    )
    return ResearchIntelligenceSummaryResponse(
        snapshot_id=snapshot.id,
        generated_at=snapshot.generated_at,
        intelligence_version=snapshot.intelligence_version,
        source_count=snapshot.source_count,
        snapshot_count=snapshot.snapshot_count,
        evidence_count=snapshot.evidence_count,
        finding_count=snapshot.finding_count,
        market_signal_count=counts["market"],
        customer_signal_count=counts["customer"],
        competitor_count=competitor_count,
        competitor_signal_count=counts["competitor"],
        freshness=snapshot.freshness,
        coverage=snapshot.coverage_json,
        missing_research_areas=snapshot.missing_areas_json,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/snapshot",
    response_model=ResearchIntelligenceSnapshotResponse,
    summary="Get the latest deterministic intelligence snapshot",
)
async def research_intelligence_snapshot(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    research_project_id: Annotated[uuid.UUID | None, Query()] = None,
) -> ResearchIntelligenceSnapshotResponse:
    business = await get_business(session, business_id)
    snapshot = await research_intelligence.ResearchIntelligenceStore(session).ensure_snapshot(
        business, research_project_id
    )
    return ResearchIntelligenceSnapshotResponse(
        snapshot_id=snapshot.id,
        research_project_id=snapshot.research_project_id,
        generated_at=snapshot.generated_at,
        source_count=snapshot.source_count,
        snapshot_count=snapshot.snapshot_count,
        evidence_count=snapshot.evidence_count,
        finding_count=snapshot.finding_count,
        intelligence_version=snapshot.intelligence_version,
        freshness=snapshot.freshness,
        coverage=snapshot.coverage_json,
        missing_research_areas=snapshot.missing_areas_json,
    )


@router.get(
    "/businesses/{business_id}/research/intelligence/snapshots/{snapshot_id}",
    response_model=ResearchIntelligenceSnapshotResponse,
    summary="Get a stored intelligence snapshot",
)
async def research_intelligence_snapshot_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    snapshot_id: uuid.UUID,
) -> ResearchIntelligenceSnapshotResponse:
    business = await get_business(session, business_id)
    snapshot = await research_intelligence.ResearchIntelligenceStore(session).get_snapshot(
        business, snapshot_id
    )
    if snapshot is None:
        raise _not_found("intelligence snapshot", snapshot_id)
    return ResearchIntelligenceSnapshotResponse(
        snapshot_id=snapshot.id,
        research_project_id=snapshot.research_project_id,
        generated_at=snapshot.generated_at,
        source_count=snapshot.source_count,
        snapshot_count=snapshot.snapshot_count,
        evidence_count=snapshot.evidence_count,
        finding_count=snapshot.finding_count,
        intelligence_version=snapshot.intelligence_version,
        freshness=snapshot.freshness,
        coverage=snapshot.coverage_json,
        missing_research_areas=snapshot.missing_areas_json,
    )


def _collection_invalid(message: str) -> ApiError:
    return CollectionRequestError(message, details={"phase": "6B"})


async def _queue_collection(
    session, business, project, payload, user, source: ResearchSource | None = None
) -> ResearchCollectionJob:
    try:
        job = await collection_service.create_job(
            session, business, project, payload, user.id, source=source
        )
    except (URLPolicyError, CollectionError) as exc:
        raise _collection_invalid(str(exc)) from exc
    await collection_jobs.enqueue_collection_job(job.id)
    return job


@router.post(
    "/businesses/{business_id}/research/projects/{project_id}/collect",
    response_model=ResearchCollectionJobResponse,
    status_code=202,
    summary="Queue public research collection",
)
async def research_collection_create(
    payload: ResearchCollectionRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
    project_id: uuid.UUID = _PROJECT_ID,
) -> ResearchCollectionJobResponse:
    business = await get_business(session, business_id)
    project = await _get_project_or_404(session, business, project_id)
    job = await _queue_collection(session, business, project, payload, user)
    return ResearchCollectionJobResponse.model_validate(job)


@router.get(
    "/businesses/{business_id}/research/collections",
    response_model=ResearchCollectionJobListResponse,
    summary="List collection jobs",
)
async def research_collection_list(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> ResearchCollectionJobListResponse:
    business = await get_business(session, business_id)
    rows, total = await collection_service.list_jobs(session, business, limit)
    return ResearchCollectionJobListResponse(
        collections=[ResearchCollectionJobResponse.model_validate(row) for row in rows], total=total
    )


@router.get(
    "/businesses/{business_id}/research/collections/{collection_id}",
    response_model=ResearchCollectionJobResponse,
    summary="Get a collection job",
)
async def research_collection_get(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    collection_id: uuid.UUID,
) -> ResearchCollectionJobResponse:
    business = await get_business(session, business_id)
    job = await collection_service.get_job(session, business, collection_id)
    if job is None:
        raise _not_found("collection job", collection_id)
    return ResearchCollectionJobResponse.model_validate(job)


async def _source_for_collection(session, business, source_id: uuid.UUID) -> ResearchSource:
    source = await _get_store(session).get_source(business, source_id)
    if source is None:
        raise _not_found("research source", source_id)
    return source


@router.post(
    "/businesses/{business_id}/research/sources/{source_id}/refresh",
    response_model=ResearchCollectionJobResponse,
    status_code=202,
    summary="Refresh a public research source",
)
async def research_source_refresh(
    payload: ResearchCollectionRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
    source_id: uuid.UUID = _SOURCE_ID,
) -> ResearchCollectionJobResponse:
    business = await get_business(session, business_id)
    source = await _source_for_collection(session, business, source_id)
    if payload.source_url is None:
        payload.source_url = source.normalized_url or source.url
    project_id = payload.research_project_id
    if not project_id:
        raise _collection_invalid("refresh requires a research project")
    project = await _get_project_or_404(session, business, project_id)
    job = await _queue_collection(session, business, project, payload, user, source)
    return ResearchCollectionJobResponse.model_validate(job)


@router.post(
    "/businesses/{business_id}/research/sources/{source_id}/crawl",
    response_model=ResearchCollectionJobResponse,
    status_code=202,
    summary="Queue limited same-domain collection",
)
async def research_source_crawl(
    payload: ResearchCollectionRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    user: CurrentUser,
    source_id: uuid.UUID = _SOURCE_ID,
) -> ResearchCollectionJobResponse:
    payload.mode = "site_limited"
    business = await get_business(session, business_id)
    source = await _source_for_collection(session, business, source_id)
    project_id = payload.research_project_id
    if not project_id:
        raise _collection_invalid("crawl requires a research project")
    project = await _get_project_or_404(session, business, project_id)
    return ResearchCollectionJobResponse.model_validate(
        await _queue_collection(session, business, project, payload, user, source)
    )


@router.post(
    "/businesses/{business_id}/research/collections/{collection_id}/cancel",
    response_model=ResearchCollectionCancelResponse,
    summary="Cancel a queued collection",
)
async def research_collection_cancel(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    collection_id: uuid.UUID,
) -> ResearchCollectionCancelResponse:
    business = await get_business(session, business_id)
    job = await collection_service.get_job(session, business, collection_id)
    if job is None:
        raise _not_found("collection job", collection_id)
    job = await collection_service.cancel_job(session, business, job)
    return ResearchCollectionCancelResponse(
        collection=ResearchCollectionJobResponse.model_validate(job)
    )


__all__ = ["router"]
