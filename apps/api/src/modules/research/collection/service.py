"""Persistence and worker orchestration for deterministic collections."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import desc, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Business,
    ResearchCollectionJob,
    ResearchCollectionPage,
    ResearchEvidence,
    ResearchProject,
    ResearchSource,
    ResearchSourceSnapshot,
)
from src.modules.research.collection.provider import (
    CollectionError,
    CollectionRequest,
    CollectionTransientError,
    WebsiteCollectionProvider,
)
from src.modules.research.collection.security import URLPolicyError, validate_public_url


def _now() -> datetime:
    return datetime.now(UTC)


async def create_job(
    session: AsyncSession,
    business: Business,
    project: ResearchProject,
    request: Any,
    user_id: uuid.UUID | None,
    *,
    source: ResearchSource | None = None,
) -> ResearchCollectionJob:
    source_url = request.source_url or (source.original_url or source.url if source else None)
    if not source_url:
        raise URLPolicyError("a public source URL is required")
    normalized = await validate_public_url(source_url)
    if source is None:
        source = await session.scalar(
            select(ResearchSource).where(
                ResearchSource.business_id == business.id,
                or_(
                    ResearchSource.normalized_url == normalized,
                    ResearchSource.url == source_url,
                ),
            )
        )
    if source is None:
        source = ResearchSource(
            organization_id=business.organization_id,
            business_id=business.id,
            source_type="website",
            title=urlsplit(normalized).hostname or normalized,
            url=source_url,
            original_url=source_url,
            normalized_url=normalized,
            domain=urlsplit(normalized).hostname,
            metadata_json={"collection_provider": "website"},
            created_by=user_id,
        )
        session.add(source)
        await session.flush()
    else:
        source.original_url = source.original_url or source.url or source_url
        source.normalized_url = normalized
    if request.mode == "specific_urls" and not request.specific_urls:
        raise CollectionError("specific_urls mode requires at least one URL")
    job = ResearchCollectionJob(
        organization_id=business.organization_id,
        business_id=business.id,
        research_project_id=project.id,
        source_id=source.id,
        provider="website",
        mode=request.mode,
        max_pages=request.max_pages,
        max_depth=request.max_depth,
        same_domain=request.same_domain,
        refresh=request.refresh,
        requested_urls=request.specific_urls or [normalized],
        idempotency_key=request.idempotency_key,
        created_by=user_id,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        if request.idempotency_key:
            existing = await session.scalar(
                select(ResearchCollectionJob).where(
                    ResearchCollectionJob.business_id == business.id,
                    ResearchCollectionJob.idempotency_key == request.idempotency_key,
                )
            )
            if existing:
                return existing
        raise
    await session.refresh(job)
    return job


async def list_jobs(
    session: AsyncSession, business: Business, limit: int = 100
) -> tuple[list[ResearchCollectionJob], int]:
    base = select(ResearchCollectionJob).where(ResearchCollectionJob.business_id == business.id)
    rows = list(
        (
            await session.scalars(
                base.order_by(desc(ResearchCollectionJob.created_at)).limit(limit)
            )
        ).all()
    )
    total = int(await session.scalar(select(func.count()).select_from(base.subquery())) or 0)
    return rows, total


async def get_job(
    session: AsyncSession, business: Business, job_id: uuid.UUID
) -> ResearchCollectionJob | None:
    return await session.scalar(
        select(ResearchCollectionJob).where(
            ResearchCollectionJob.id == job_id, ResearchCollectionJob.business_id == business.id
        )
    )


async def cancel_job(
    session: AsyncSession, business: Business, job: ResearchCollectionJob
) -> ResearchCollectionJob:
    if job.status in {"queued", "running"}:
        job.status = "cancelled"
        job.completed_at = _now()
        await session.commit()
        await session.refresh(job)
    return job


async def run_job(session: AsyncSession, job_id: uuid.UUID) -> ResearchCollectionJob:
    job = await session.get(ResearchCollectionJob, job_id)
    if job is None:
        raise CollectionError("collection job not found")
    if job.status == "cancelled":
        return job
    source = await session.get(ResearchSource, job.source_id) if job.source_id else None
    if source is None:
        job.status, job.error = "failed", "source not found"
        job.completed_at = _now()
        await session.commit()
        return job
    job.status = "running"
    job.started_at = job.started_at or _now()
    job.attempts += 1
    await session.commit()
    request = CollectionRequest(
        url=source.normalized_url or source.url or job.requested_urls[0],
        mode=job.mode,
        max_pages=job.max_pages,
        max_depth=job.max_depth,
        same_domain=job.same_domain,
        specific_urls=tuple(job.requested_urls),
    )
    try:
        previous_hash = source.content_hash
        pages = await WebsiteCollectionProvider().collect(request)
        changed = "first_seen" if previous_hash is None else "unchanged"
        for collected in pages:
            if await session.scalar(
                select(ResearchCollectionPage.id).where(
                    ResearchCollectionPage.collection_job_id == job.id,
                    ResearchCollectionPage.normalized_url == collected.normalized_url,
                )
            ):
                continue
            page = ResearchCollectionPage(
                collection_job_id=job.id,
                source_id=source.id,
                original_url=collected.original_url,
                normalized_url=collected.normalized_url,
                http_status=collected.status_code,
                content_type=collected.content_type,
                title=collected.extracted.get("title"),
                canonical_url=collected.extracted.get("canonical_url"),
                content_hash=collected.content_hash,
                content=collected.content,
                metadata_json={
                    "provider": "website",
                    "final_url": collected.final_url,
                    "redirect_count": collected.redirect_count,
                    "response_size": collected.response_size,
                    "duration_ms": collected.duration_ms,
                    "parser_version": "1",
                },
                response_size=collected.response_size,
                duration_ms=collected.duration_ms,
                depth=collected.depth,
                retrieved_at=collected.retrieved_at,
            )
            session.add(page)
            await session.flush()
            snapshot = await session.scalar(
                select(ResearchSourceSnapshot).where(
                    ResearchSourceSnapshot.source_id == source.id,
                    ResearchSourceSnapshot.content_hash == collected.content_hash,
                )
            )
            if snapshot is None:
                snapshot = ResearchSourceSnapshot(
                    source_id=source.id,
                    content_hash=collected.content_hash,
                    content=collected.content,
                    captured_at=collected.retrieved_at,
                    metadata_json={
                        "provider": "website",
                        "http_status": collected.status_code,
                        "content_type": collected.content_type,
                        "final_url": collected.final_url,
                    },
                )
                session.add(snapshot)
                await session.flush()
            else:
                changed = "unchanged"
            for signal in _observable_signals(
                collected, source, job.research_project_id, snapshot.id
            ):
                session.add(ResearchEvidence(**signal))
            source.content_hash = collected.content_hash
            if previous_hash is not None and previous_hash != collected.content_hash:
                changed = "changed"
            source.captured_at = collected.retrieved_at
            source.metadata_json = {
                **(source.metadata_json or {}),
                "last_collected": collected.retrieved_at.isoformat(),
            }
        job.pages_collected = len(pages)
        job.change_status = changed
        job.status = "completed"
        job.completed_at = _now()
        job.error = None
        await session.commit()
        await session.refresh(job)
        return job
    except CollectionTransientError:
        job.status = "queued"
        await session.commit()
        raise
    except (CollectionError, URLPolicyError) as exc:
        job.status, job.error = "failed", str(exc)
        job.completed_at = _now()
        await session.commit()
        return job


def _observable_signals(
    collected: Any, source: ResearchSource, project_id: uuid.UUID, snapshot_id: uuid.UUID
) -> list[dict[str, Any]]:
    from src.modules.research.collection.extract import observable_signals

    result = []
    for signal in observable_signals(collected.extracted):
        result.append(
            {
                "organization_id": source.organization_id,
                "business_id": source.business_id,
                "source_id": source.id,
                "research_project_id": project_id,
                "snapshot_id": snapshot_id,
                "evidence_type": signal["type"],
                "statement": signal["statement"],
                "raw_excerpt": collected.content[:2000],
                "structured_value": signal.get("value"),
                "confidence": "observed",
                "provenance": "collected",
                "captured_at": collected.retrieved_at,
            }
        )
    return result
