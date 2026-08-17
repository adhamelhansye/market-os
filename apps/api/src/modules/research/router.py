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
from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query

from src.core.dependencies import (
    CurrentBusinessId,
    CurrentUser,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import (
    ResearchCompetitor,
    ResearchEvidence,
    ResearchFinding,
    ResearchProject,
    ResearchSource,
)
from src.modules.businesses.service import get_business
from src.modules.research import service as research_service
from src.modules.research.schemas import (
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
    updated = await _get_store(session).set_project_status(
        business, project, request=payload
    )
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
    source = await _get_store(session).create_source(
        business, request=payload, created_by=user.id
    )
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


__all__ = ["router"]
