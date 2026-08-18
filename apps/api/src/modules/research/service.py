"""Research service: deterministic storage layer for research intelligence.

Implements the Source → Snapshot → Evidence → Finding chain. The service
is the only component that touches the research tables. It performs NO
external requests, NO scraping, NO LLM calls and NO autonomous action:
clients submit candidate content; the service validates tenancy,
vocabulary, classification rules and deduplicates by content hash.

Deterministic classification rules:

- evidence confidence defaults to `observed` unless the submitter sets
  an explicit lower value, or the claim is clearly unverified
  (hypothesis);
- evidence carrying BOTH a raw excerpt AND a structured value implies
  reasoning was applied, so the submitter must explicitly confirm
  `inferred` (rejecting a claimed `observed`/`supported` with a
  `requires_confirmation` error carrying the rule id);
- finding classification defaults to `inferred` when evidence is
  attached and `hypothesis` when none is attached; `observed` requires
  supporting evidence; a `hypothesis` finding must NOT carry evidence —
  violations raise confirmation errors;
- evidence strength for a finding is derived deterministically from the
  attached evidence (see `evidence_strength_ladder`).

Financial values inside JSONB are stored as Decimal-as-string (never
float) via `_money_safe_json`.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from collections import Counter
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import asc, desc, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Business,
    ResearchCompetitor,
    ResearchEvidence,
    ResearchFinding,
    ResearchProject,
    ResearchSource,
    ResearchSourceSnapshot,
    research_finding_evidence,
)
from src.modules.research.constants import (
    FINDING_CATEGORIES,
    PROJECT_STATUS_TRANSITIONS,
    evidence_strength_ladder,
)
from src.modules.research.errors import (
    ResearchClassificationError,
    ResearchConfirmationError,
    ResearchInvalidStateError,
    ResearchNotFoundError,
    ResearchResourceConflictError,
)
from src.modules.research.schemas import (
    ResearchCompetitorCreateRequest,
    ResearchEvidenceCreateRequest,
    ResearchFindingCreateRequest,
    ResearchProjectCreateRequest,
    ResearchProjectStatusRequest,
    ResearchSearchHitResponse,
    ResearchSourceCreateRequest,
    validate_classification,
    validate_evidence_type,
    validate_finding_category,
    validate_importance,
    validate_project_status,
    validate_project_type,
    validate_provenance,
    validate_source_type,
)

# Keys whose numeric values must be stored as Decimal strings in JSONB.
_MONEY_KEYS = frozenset(
    {
        "amount",
        "aov",
        "budget",
        "cac",
        "cost",
        "cpa",
        "discount_value",
        "ltv",
        "mer",
        "price",
        "profit",
        "revenue",
        "roas",
        "spend",
        "value",
    }
)


def _money_safe_json(value: Any) -> Any:
    """Recursively stringify money values (Decimal-as-string rule)."""
    if isinstance(value, dict):
        return {
            key: (
                str(value[key])
                if key in _MONEY_KEYS and isinstance(value[key], float)
                else _money_safe_json(value[key])
            )
            for key in value
        }
    if isinstance(value, list):
        return [_money_safe_json(v) for v in value]
    return value


class ResearchStore:
    """Deterministic storage for the research layer under one business.

    Receives the request-scoped AsyncSession (managed by the FastAPI
    dependency) and commits explicitly; it never opens or closes
    sessions itself.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session_factory = session

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _canonical_hash(payload: ResearchSourceCreateRequest) -> str | None:
        if not payload.content:
            return None
        canonical = {
            "source_type": payload.source_type,
            "title": payload.title,
            "url": payload.url,
            "author": payload.author,
            "published_at": payload.published_at.isoformat() if payload.published_at else None,
            "content": payload.content,
            "metadata": payload.metadata,
        }
        raw = json.dumps(canonical, sort_keys=True, ensure_ascii=False).encode("utf-8")
        return hashlib.sha256(raw).hexdigest()

    @staticmethod
    def _derived_domain(url: str | None) -> str | None:
        if not url:
            return None
        host = urlsplit(url).hostname
        return host.lower() if host else None

    # ------------------------------------------------------------------
    # Projects
    # ------------------------------------------------------------------
    async def create_project(
        self,
        business: Business,
        *,
        request: ResearchProjectCreateRequest,
        created_by: uuid.UUID | None,
    ) -> ResearchProject:
        validate_project_type(request.type)
        session = self._session_factory
        project = ResearchProject(
            organization_id=business.organization_id,
            business_id=business.id,
            name=request.name.strip(),
            type=request.type,
            scope=request.scope or None,
            status="draft",
            created_by=created_by,
        )
        session.add(project)
        await session.commit()
        await session.refresh(project)
        return project

    async def list_projects(
        self, business: Business, *, limit: int = 100
    ) -> tuple[list[ResearchProject], int]:
        session = self._session_factory
        total = int(
            await session.scalar(
                select(func.count())
                .select_from(ResearchProject)
                .where(
                    ResearchProject.organization_id == business.organization_id,
                    ResearchProject.business_id == business.id,
                )
            )
            or 0
        )
        rows = list(
            await session.scalars(
                select(ResearchProject)
                .where(
                    ResearchProject.organization_id == business.organization_id,
                    ResearchProject.business_id == business.id,
                )
                .order_by(desc(ResearchProject.created_at))
                .limit(limit)
            )
        )
        return rows, total

    async def get_project(
        self, business: Business, project_id: uuid.UUID
    ) -> ResearchProject | None:
        session = self._session_factory
        return await session.scalar(
            select(ResearchProject).where(
                ResearchProject.organization_id == business.organization_id,
                ResearchProject.business_id == business.id,
                ResearchProject.id == project_id,
            )
        )

    async def set_project_status(
        self,
        business: Business,
        project: ResearchProject,
        *,
        request: ResearchProjectStatusRequest,
    ) -> ResearchProject:
        requested = validate_project_status(request.status)
        allowed = PROJECT_STATUS_TRANSITIONS[project.status]
        if requested not in allowed:
            raise ResearchInvalidStateError(project.status, requested, allowed)
        session = self._session_factory
        stored = await session.get(ResearchProject, project.id)
        stored.status = requested
        stored.updated_at = datetime.now(UTC)
        await session.commit()
        await session.refresh(stored)
        return stored

    async def project_summary(self, business: Business, project_id: uuid.UUID) -> dict[str, Any]:
        """Deterministic data-quality summary for a project detail."""
        session = self._session_factory
        where_evidence = [
            ResearchEvidence.organization_id == business.organization_id,
            ResearchEvidence.business_id == business.id,
        ]
        evidence_count = int(
            await session.scalar(
                select(func.count()).select_from(ResearchEvidence).where(*where_evidence)
            )
            or 0
        )
        where_source = [
            ResearchSource.organization_id == business.organization_id,
            ResearchSource.business_id == business.id,
        ]
        source_count = int(
            await session.scalar(
                select(func.count()).select_from(ResearchSource).where(*where_source)
            )
            or 0
        )
        where_competitor = [
            ResearchCompetitor.organization_id == business.organization_id,
            ResearchCompetitor.business_id == business.id,
        ]
        competitor_count = int(
            await session.scalar(
                select(func.count()).select_from(ResearchCompetitor).where(*where_competitor)
            )
            or 0
        )
        where_finding = [
            ResearchFinding.organization_id == business.organization_id,
            ResearchFinding.business_id == business.id,
            ResearchFinding.research_project_id == project_id,
        ]
        finding_count = int(
            await session.scalar(
                select(func.count()).select_from(ResearchFinding).where(*where_finding)
            )
            or 0
        )
        covered = set(await session.scalars(select(ResearchFinding.category).where(*where_finding)))
        total_categories = len(FINDING_CATEGORIES)
        coverage = {
            "status": "available" if total_categories > 0 else "unavailable",
            "covered_categories": len(covered),
            "total_categories": total_categories,
            "missing_areas": sorted(FINDING_CATEGORIES.difference(covered)),
        }
        if total_categories == 0:
            coverage["reason"] = "no finding categories configured"
        latest = list(
            await session.scalars(
                select(ResearchEvidence.captured_at)
                .where(*where_evidence)
                .order_by(desc(ResearchEvidence.captured_at))
                .limit(1)
            )
        )
        freshness = latest[0] if latest else None
        evidence_by_type = dict(
            Counter(
                row[0]
                for row in await session.execute(
                    select(ResearchEvidence.evidence_type).where(*where_evidence)
                )
            )
        )
        strength_counts: dict[str, int] = {}
        for strength in ("strong", "moderate", "weak", "insufficient"):
            strength_counts[strength] = int(
                await session.scalar(
                    select(func.count())
                    .select_from(ResearchFinding)
                    .where(*where_finding, ResearchFinding.evidence_strength == strength)
                )
                or 0
            )
        return {
            "source_count": source_count,
            "competitor_count": competitor_count,
            "evidence_count": evidence_count,
            "finding_count": finding_count,
            "strength_distribution": strength_counts,
            "evidence_by_type": evidence_by_type,
            "coverage": coverage,
            "missing_areas": sorted(FINDING_CATEGORIES.difference(covered)),
            "freshness": freshness.isoformat() if freshness else None,
        }

    # ------------------------------------------------------------------
    # Competitors
    # ------------------------------------------------------------------
    async def create_competitor(
        self,
        business: Business,
        *,
        request: ResearchCompetitorCreateRequest,
        created_by: uuid.UUID | None,
    ) -> ResearchCompetitor:
        session = self._session_factory
        duplicate = await session.scalar(
            select(ResearchCompetitor).where(
                ResearchCompetitor.organization_id == business.organization_id,
                ResearchCompetitor.business_id == business.id,
                func.lower(ResearchCompetitor.name) == request.name.strip().lower(),
            )
        )
        if duplicate is not None:
            raise ResearchResourceConflictError(
                "duplicate_competitor",
                {"competitor_id": str(duplicate.id), "name": duplicate.name},
            )
        competitor = ResearchCompetitor(
            organization_id=business.organization_id,
            business_id=business.id,
            name=request.name.strip(),
            domain=request.domain or None,
            description=request.description or None,
            market=request.market or None,
            status=request.status or "active",
            metadata_json=_money_safe_json(request.metadata or {}),
            created_by=created_by,
        )
        session.add(competitor)
        await session.commit()
        await session.refresh(competitor)
        return competitor

    async def list_competitors(
        self, business: Business, *, limit: int = 100
    ) -> tuple[list[ResearchCompetitor], int]:
        session = self._session_factory
        where = [
            ResearchCompetitor.organization_id == business.organization_id,
            ResearchCompetitor.business_id == business.id,
        ]
        total = int(
            await session.scalar(select(func.count()).select_from(ResearchCompetitor).where(*where))
            or 0
        )
        rows = list(
            await session.scalars(
                select(ResearchCompetitor)
                .where(*where)
                .order_by(asc(ResearchCompetitor.name))
                .limit(limit)
            )
        )
        return rows, total

    async def get_competitor(
        self, business: Business, competitor_id: uuid.UUID
    ) -> ResearchCompetitor | None:
        session = self._session_factory
        return await session.scalar(
            select(ResearchCompetitor).where(
                ResearchCompetitor.organization_id == business.organization_id,
                ResearchCompetitor.business_id == business.id,
                ResearchCompetitor.id == competitor_id,
            )
        )

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------
    async def create_source(
        self,
        business: Business,
        *,
        request: ResearchSourceCreateRequest,
        created_by: uuid.UUID | None,
    ) -> ResearchSource:
        validate_source_type(request.source_type)
        content_hash = self._canonical_hash(request)
        domain = request.domain or self._derived_domain(request.url)
        session = self._session_factory
        if request.competitor_id is not None:
            competitor = await session.scalar(
                select(ResearchCompetitor).where(
                    ResearchCompetitor.organization_id == business.organization_id,
                    ResearchCompetitor.business_id == business.id,
                    ResearchCompetitor.id == request.competitor_id,
                )
            )
            if competitor is None:
                raise ResearchNotFoundError("competitor", str(request.competitor_id))
        if content_hash is not None:
            existing = await session.scalar(
                select(ResearchSource).where(
                    ResearchSource.organization_id == business.organization_id,
                    ResearchSource.business_id == business.id,
                    ResearchSource.content_hash == content_hash,
                )
            )
            if existing is not None:
                return existing  # idempotent: identical content collapses
        source = ResearchSource(
            organization_id=business.organization_id,
            business_id=business.id,
            source_type=request.source_type,
            title=request.title.strip(),
            url=request.url or None,
            original_url=request.url or None,
            normalized_url=request.url or None,
            domain=domain,
            author=request.author or None,
            published_at=request.published_at,
            content_hash=content_hash,
            metadata_json=_money_safe_json(request.metadata or {}),
            status="active",
            competitor_id=request.competitor_id,
            created_by=created_by,
        )
        session.add(source)
        await session.flush()
        if content_hash is not None:
            session.add(
                ResearchSourceSnapshot(
                    source_id=source.id,
                    content_hash=content_hash,
                    content=request.content or "",
                    metadata_json={},
                )
            )
        await session.commit()
        await session.refresh(source)
        return source

    async def list_sources(
        self,
        business: Business,
        *,
        source_type: str | None = None,
        competitor_id: uuid.UUID | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[list[ResearchSource], int]:
        session = self._session_factory
        where = [
            ResearchSource.organization_id == business.organization_id,
            ResearchSource.business_id == business.id,
        ]
        if source_type:
            where.append(ResearchSource.source_type == source_type)
        if competitor_id is not None:
            where.append(ResearchSource.competitor_id == competitor_id)
        if status:
            where.append(ResearchSource.status == status)
        total = int(
            await session.scalar(select(func.count()).select_from(ResearchSource).where(*where))
            or 0
        )
        rows = list(
            await session.scalars(
                select(ResearchSource)
                .where(*where)
                .order_by(desc(ResearchSource.created_at))
                .limit(limit)
            )
        )
        return rows, total

    async def get_source(self, business: Business, source_id: uuid.UUID) -> ResearchSource | None:
        session = self._session_factory
        return await session.scalar(
            select(ResearchSource).where(
                ResearchSource.organization_id == business.organization_id,
                ResearchSource.business_id == business.id,
                ResearchSource.id == source_id,
            )
        )

    async def get_source_snapshots(self, source: ResearchSource) -> list[ResearchSourceSnapshot]:
        session = self._session_factory
        return list(
            await session.scalars(
                select(ResearchSourceSnapshot)
                .where(ResearchSourceSnapshot.source_id == source.id)
                .order_by(desc(ResearchSourceSnapshot.captured_at))
            )
        )

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------
    async def create_evidence(
        self,
        business: Business,
        *,
        request: ResearchEvidenceCreateRequest,
        created_by: uuid.UUID | None,
    ) -> ResearchEvidence:
        validate_evidence_type(request.evidence_type)
        classification = validate_classification(request.classification)
        validate_provenance(request.provenance)
        session = self._session_factory
        source = await session.scalar(
            select(ResearchSource).where(
                ResearchSource.organization_id == business.organization_id,
                ResearchSource.business_id == business.id,
                ResearchSource.id == request.source_id,
            )
        )
        if source is None:
            raise ResearchNotFoundError("source", str(request.source_id))

        # Deterministic quality rule: explicit reasoning applied
        # (raw excerpt + structured value) is no longer pure
        # observation — reject unless the submitter explicitly
        # classifies it inferred or weaker.
        if request.raw_excerpt and request.structured_value and classification == "observed":
            raise ResearchConfirmationError(
                classification="inferred",
                reasons=["excerpt_and_structured_value"],
                details=[
                    "Evidence with both a raw excerpt and a structured value "
                    "implies reasoning; re-submit with classification=inferred."
                ],
            )

        evidence = ResearchEvidence(
            organization_id=business.organization_id,
            business_id=business.id,
            source_id=source.id,
            evidence_type=request.evidence_type,
            statement=request.statement.strip(),
            raw_excerpt=request.raw_excerpt,
            structured_value=_money_safe_json(request.structured_value),
            unit=request.unit or None,
            captured_at=request.captured_at or datetime.now(UTC),
            confidence=classification,
            provenance=request.provenance,
            created_by=created_by,
        )
        session.add(evidence)
        await session.commit()
        await session.refresh(evidence)
        return evidence

    async def list_evidence(
        self,
        business: Business,
        *,
        evidence_type: str | None = None,
        source_id: uuid.UUID | None = None,
        classification: str | None = None,
        confidence: str | None = None,
        provenance: str | None = None,
        limit: int = 100,
    ) -> tuple[list[ResearchEvidence], int]:
        session = self._session_factory
        where = [
            ResearchEvidence.organization_id == business.organization_id,
            ResearchEvidence.business_id == business.id,
        ]
        if evidence_type:
            where.append(ResearchEvidence.evidence_type == evidence_type)
        if source_id is not None:
            where.append(ResearchEvidence.source_id == source_id)
        if classification or confidence:
            where.append(ResearchEvidence.confidence == (classification or confidence))
        if provenance:
            where.append(ResearchEvidence.provenance == provenance)
        total = int(
            await session.scalar(select(func.count()).select_from(ResearchEvidence).where(*where))
            or 0
        )
        rows = list(
            await session.scalars(
                select(ResearchEvidence)
                .where(*where)
                .order_by(desc(ResearchEvidence.created_at))
                .limit(limit)
            )
        )
        return rows, total

    # ------------------------------------------------------------------
    # Findings
    # ------------------------------------------------------------------
    async def create_finding(
        self,
        business: Business,
        *,
        request: ResearchFindingCreateRequest,
        created_by: uuid.UUID | None,
    ) -> ResearchFinding:
        validate_finding_category(request.category)
        validate_importance(request.importance)
        if request.classification is not None:
            validate_classification(request.classification)
        session = self._session_factory
        project = await session.scalar(
            select(ResearchProject).where(
                ResearchProject.organization_id == business.organization_id,
                ResearchProject.business_id == business.id,
                ResearchProject.id == request.research_project_id,
            )
        )
        if project is None:
            raise ResearchNotFoundError("project", str(request.research_project_id))

        evidence_ids = request.evidence_ids
        valid_ids: list[uuid.UUID] = []
        if evidence_ids:
            rows = list(
                await session.scalars(
                    select(ResearchEvidence.id).where(
                        ResearchEvidence.organization_id == business.organization_id,
                        ResearchEvidence.business_id == business.id,
                        ResearchEvidence.id.in_(evidence_ids),
                    )
                )
            )
            valid_ids = sorted(set(rows))
            missing = [str(eid) for eid in evidence_ids if eid not in set(valid_ids)]
            if missing:
                raise ResearchNotFoundError("evidence", missing[0])
        if not valid_ids:
            raise ResearchConfirmationError(
                classification=request.classification or "inferred",
                reasons=["finding_requires_evidence"],
                details=["A finding must reference at least one evidence record."],
            )

        # Deterministic default classification ladder:
        #   evidence attached -> inferred
        #   explicit observed -> only with supporting evidence
        classification = request.classification
        if classification is None:
            classification = "inferred"
        if classification not in ("observed", "inferred", "hypothesis"):
            raise ResearchClassificationError(
                "finding.classification",
                classification,
                frozenset({"observed", "inferred", "hypothesis"}),
            )
        if classification == "observed" and not valid_ids:
            raise ResearchConfirmationError(
                classification="observed",
                reasons=["observed_requires_evidence"],
                details=["An observed finding must reference at least one evidence row."],
            )

        corroborated = 0
        if valid_ids:
            corroborated = len(
                list(
                    await session.scalars(
                        select(ResearchEvidence.id).where(
                            ResearchEvidence.organization_id == business.organization_id,
                            ResearchEvidence.business_id == business.id,
                            ResearchEvidence.id.in_(valid_ids),
                            ResearchEvidence.confidence.in_(["observed", "supported"]),
                        )
                    )
                )
            )

        finding = ResearchFinding(
            organization_id=business.organization_id,
            business_id=business.id,
            research_project_id=project.id,
            category=request.category,
            title=request.title.strip(),
            statement=request.statement.strip(),
            classification=classification,
            importance=request.importance,
            evidence_strength=evidence_strength_ladder(len(valid_ids), corroborated),
            created_by=created_by,
        )
        session.add(finding)
        await session.flush()
        for evidence_id in valid_ids:
            await session.execute(
                research_finding_evidence.insert().values(
                    finding_id=finding.id, evidence_id=evidence_id
                )
            )
        await session.commit()
        await session.refresh(finding)
        return finding

    async def list_findings(
        self,
        business: Business,
        *,
        research_project_id: uuid.UUID | None = None,
        category: str | None = None,
        classification: str | None = None,
        importance: str | None = None,
        limit: int = 100,
    ) -> tuple[list[ResearchFinding], int]:
        session = self._session_factory
        where = [
            ResearchFinding.organization_id == business.organization_id,
            ResearchFinding.business_id == business.id,
        ]
        if research_project_id is not None:
            where.append(ResearchFinding.research_project_id == research_project_id)
        if category:
            where.append(ResearchFinding.category == category)
        if classification:
            where.append(ResearchFinding.classification == classification)
        if importance:
            where.append(ResearchFinding.importance == importance)
        total = int(
            await session.scalar(select(func.count()).select_from(ResearchFinding).where(*where))
            or 0
        )
        rows = list(
            await session.scalars(
                select(ResearchFinding)
                .where(*where)
                .order_by(desc(ResearchFinding.created_at))
                .limit(limit)
            )
        )
        return rows, total

    async def get_finding(
        self, business: Business, finding_id: uuid.UUID
    ) -> tuple[ResearchFinding, list[ResearchEvidence]] | None:
        session = self._session_factory
        finding = await session.scalar(
            select(ResearchFinding).where(
                ResearchFinding.organization_id == business.organization_id,
                ResearchFinding.business_id == business.id,
                ResearchFinding.id == finding_id,
            )
        )
        if finding is None:
            return None
        evidence = list(
            await session.scalars(
                select(ResearchEvidence)
                .join(
                    research_finding_evidence,
                    research_finding_evidence.c.evidence_id == ResearchEvidence.id,
                )
                .where(research_finding_evidence.c.finding_id == finding.id)
                .order_by(desc(ResearchEvidence.created_at))
            )
        )
        return finding, evidence

    # ------------------------------------------------------------------
    # Search (deterministic LIKE over text columns; no vector store)
    # ------------------------------------------------------------------
    async def search_research(
        self, business: Business, query: str, *, limit: int = 20
    ) -> list[ResearchSearchHitResponse]:
        pattern = f"%{query.strip()}%"
        session = self._session_factory
        hits: list[ResearchSearchHitResponse] = []

        evidence_rows = list(
            await session.scalars(
                select(ResearchEvidence)
                .join(ResearchSource, ResearchSource.id == ResearchEvidence.source_id)
                .where(
                    ResearchEvidence.organization_id == business.organization_id,
                    ResearchEvidence.business_id == business.id,
                    or_(
                        ResearchEvidence.statement.ilike(pattern),
                        ResearchEvidence.raw_excerpt.ilike(pattern),
                        ResearchSource.title.ilike(pattern),
                        ResearchSource.domain.ilike(pattern),
                    ),
                )
                .order_by(desc(ResearchEvidence.created_at))
                .limit(limit)
            )
        )
        for evidence in evidence_rows:
            source = await session.get(ResearchSource, evidence.source_id)
            hits.append(
                ResearchSearchHitResponse(
                    entity_type="evidence",
                    entity_id=evidence.id,
                    title=evidence.evidence_type,
                    statement=evidence.statement,
                    source_id=evidence.source_id,
                    source_title=source.title if source else None,
                    source_domain=source.domain if source else None,
                    evidence_type=evidence.evidence_type,
                    classification=evidence.confidence,
                    captured_at=evidence.captured_at,
                )
            )

        source_rows = list(
            await session.scalars(
                select(ResearchSource)
                .where(
                    ResearchSource.organization_id == business.organization_id,
                    ResearchSource.business_id == business.id,
                    or_(
                        ResearchSource.title.ilike(pattern),
                        ResearchSource.domain.ilike(pattern),
                    ),
                )
                .order_by(desc(ResearchSource.created_at))
                .limit(limit)
            )
        )
        for source in source_rows:
            hits.append(
                ResearchSearchHitResponse(
                    entity_type="source",
                    entity_id=source.id,
                    title=source.title,
                    statement=source.url or source.domain,
                    source_id=source.id,
                    source_title=source.title,
                    source_domain=source.domain,
                    captured_at=source.captured_at,
                )
            )

        finding_rows = list(
            await session.scalars(
                select(ResearchFinding)
                .where(
                    ResearchFinding.organization_id == business.organization_id,
                    ResearchFinding.business_id == business.id,
                    or_(
                        ResearchFinding.title.ilike(pattern),
                        ResearchFinding.statement.ilike(pattern),
                    ),
                )
                .order_by(desc(ResearchFinding.created_at))
                .limit(limit)
            )
        )
        for finding in finding_rows:
            hits.append(
                ResearchSearchHitResponse(
                    entity_type="finding",
                    entity_id=finding.id,
                    title=finding.title,
                    statement=finding.statement,
                    classification=finding.classification,
                    captured_at=finding.created_at,
                )
            )

        competitor_rows = list(
            await session.scalars(
                select(ResearchCompetitor)
                .where(
                    ResearchCompetitor.organization_id == business.organization_id,
                    ResearchCompetitor.business_id == business.id,
                    ResearchCompetitor.name.ilike(pattern),
                )
                .order_by(desc(ResearchCompetitor.created_at))
                .limit(limit)
            )
        )
        for competitor in competitor_rows:
            hits.append(
                ResearchSearchHitResponse(
                    entity_type="competitor",
                    entity_id=competitor.id,
                    title=competitor.name,
                    statement=competitor.description or competitor.market,
                    source_domain=competitor.domain,
                    captured_at=competitor.created_at,
                )
            )

        hits.sort(
            key=lambda item: item.captured_at or datetime.min.replace(tzinfo=UTC),
            reverse=True,
        )
        return hits[:limit]


__all__ = ["ResearchStore"]
