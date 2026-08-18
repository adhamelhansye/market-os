"""Deterministic research intelligence aggregation.

This module deliberately performs no semantic model calls. It groups stored
evidence by explicit evidence types and exact normalized statements, creates
traceable findings for each group, and records the rule version in a
reproducible snapshot.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from collections import defaultdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Business,
    ResearchEvidence,
    ResearchFinding,
    ResearchIntelligenceItem,
    ResearchIntelligenceSnapshot,
    ResearchSource,
    ResearchSourceSnapshot,
    research_finding_evidence,
    research_intelligence_item_findings,
)

INTELLIGENCE_VERSION = "research_intelligence_v1"
FRESH_THRESHOLD = timedelta(days=30)
AGING_THRESHOLD = timedelta(days=90)
CUSTOMER_SOURCE_TYPES = frozenset({"review", "social_post", "uploaded_document", "manual"})
MONEY_KEYS = frozenset({"amount", "discount_value", "price", "value"})

_MARKET_CATEGORIES = {
    "pricing": "pricing",
    "offer": "offer",
    "messaging": "messaging",
    "market_signal": "trend",
    "competitor_gap": "gap",
    "pain_point": "problem",
    "desire": "need",
}
_CUSTOMER_CATEGORIES = {
    "pain_point": "pain_point",
    "complaint": "pain_point",
    "desire": "desire",
    "objection": "objection",
    "buying_trigger": "buying_trigger",
    "trust_signal": "trust_factor",
    "benefit": "benefit",
}
_COMPETITOR_CATEGORIES = {
    "positioning": "positioning",
    "pricing": "pricing",
    "offer": "offer",
    "product": "product",
    "feature": "feature",
    "benefit": "benefit",
    "messaging": "messaging",
    "creative_pattern": "creative_pattern",
    "trust_signal": "trust_signal",
    "review": "social_proof",
    "complaint": "complaint",
    "competitor_gap": "gap",
}


def freshness(captured_at: datetime | None, *, now: datetime | None = None) -> str:
    if captured_at is None:
        return "unknown"
    reference = now or datetime.now(UTC)
    captured = captured_at if captured_at.tzinfo else captured_at.replace(tzinfo=UTC)
    age = reference - captured
    if age <= FRESH_THRESHOLD:
        return "fresh"
    if age <= AGING_THRESHOLD:
        return "aging"
    return "stale"


def _normalize_statement(statement: str) -> str:
    return re.sub(r"\s+", " ", statement.strip().lower())


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return value


def _price(value: Any) -> tuple[str, Decimal] | None:
    if not isinstance(value, dict):
        return None
    raw = value.get("price") or value.get("amount")
    currency = value.get("currency") or value.get("priceCurrency")
    if raw is None or not currency:
        return None
    try:
        return str(currency).upper(), Decimal(str(raw).replace(",", ""))
    except (InvalidOperation, ValueError):
        return None


def _strength(
    evidence: list[ResearchEvidence],
    sources: dict[uuid.UUID, ResearchSource],
    snapshots: dict[uuid.UUID, ResearchSourceSnapshot],
    *,
    customer: bool,
) -> tuple[str, str, int]:
    source_ids = {row.source_id for row in evidence}
    content_hashes: set[str] = set()
    domains: set[str] = set()
    unknown = False
    for row in evidence:
        source = sources.get(row.source_id)
        if source is None:
            unknown = True
            continue
        snapshot = snapshots.get(row.snapshot_id) if row.snapshot_id else None
        if snapshot:
            content_hashes.add(snapshot.content_hash)
        elif source.content_hash:
            content_hashes.add(source.content_hash)
        elif source.domain:
            domains.add(source.domain.lower())
        else:
            unknown = True
    independent = len(content_hashes | domains)
    if independent == 0:
        independent = len(source_ids)
    if customer and independent >= 3:
        strength = "strong"
    elif independent >= 2:
        strength = "moderate"
    else:
        strength = "weak"
    return strength, ("unknown" if unknown else "known"), independent


def _classification(evidence: list[ResearchEvidence]) -> str:
    values = {row.confidence for row in evidence}
    if "hypothesis" in values:
        return "hypothesis"
    if "inferred" in values:
        return "inferred"
    return "observed"


def _category_for(
    intelligence_type: str, evidence_type: str, *, competitor: bool = False
) -> str | None:
    if intelligence_type == "customer":
        return _CUSTOMER_CATEGORIES.get(evidence_type)
    if intelligence_type == "competitor":
        return _COMPETITOR_CATEGORIES.get(evidence_type, "other") if competitor else None
    return _MARKET_CATEGORIES.get(evidence_type)


class ResearchIntelligenceStore:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _inputs(
        self, business: Business, project_id: uuid.UUID | None
    ) -> tuple[
        list[ResearchEvidence], dict[uuid.UUID, ResearchSource], list[ResearchSourceSnapshot]
    ]:
        evidence_where = [
            ResearchEvidence.organization_id == business.organization_id,
            ResearchEvidence.business_id == business.id,
        ]
        if project_id:
            evidence_where.append(ResearchEvidence.research_project_id == project_id)
        evidence = list(
            await self.session.scalars(
                select(ResearchEvidence).where(*evidence_where).order_by(ResearchEvidence.id)
            )
        )
        source_ids = {row.source_id for row in evidence}
        sources = {}
        if source_ids:
            sources = {
                row.id: row
                for row in await self.session.scalars(
                    select(ResearchSource).where(
                        ResearchSource.organization_id == business.organization_id,
                        ResearchSource.business_id == business.id,
                        ResearchSource.id.in_(source_ids),
                    )
                )
            }
        snapshots = list(
            await self.session.scalars(
                select(ResearchSourceSnapshot).where(
                    ResearchSourceSnapshot.source_id.in_(source_ids) if source_ids else False
                )
            )
        )
        return evidence, sources, snapshots

    async def _input_hash(
        self, evidence: list[ResearchEvidence], sources: dict[uuid.UUID, ResearchSource]
    ) -> str:
        values = [
            {
                "id": str(row.id),
                "source": str(row.source_id),
                "statement": row.statement,
                "classification": row.confidence,
                "captured_at": row.captured_at.isoformat(),
                "source_hash": sources.get(row.source_id).content_hash
                if sources.get(row.source_id)
                else None,
            }
            for row in evidence
        ]
        return hashlib.sha256(json.dumps(values, sort_keys=True).encode()).hexdigest()

    async def _latest_snapshot(
        self, business: Business, project_id: uuid.UUID | None, input_hash: str
    ) -> ResearchIntelligenceSnapshot | None:
        return await self.session.scalar(
            select(ResearchIntelligenceSnapshot)
            .where(
                ResearchIntelligenceSnapshot.organization_id == business.organization_id,
                ResearchIntelligenceSnapshot.business_id == business.id,
                ResearchIntelligenceSnapshot.research_project_id == project_id,
                ResearchIntelligenceSnapshot.input_hash == input_hash,
                ResearchIntelligenceSnapshot.intelligence_version == INTELLIGENCE_VERSION,
            )
            .order_by(desc(ResearchIntelligenceSnapshot.generated_at))
            .limit(1)
        )

    async def ensure_snapshot(
        self, business: Business, project_id: uuid.UUID | None = None
    ) -> ResearchIntelligenceSnapshot:
        evidence, sources, source_snapshots = await self._inputs(business, project_id)
        input_hash = await self._input_hash(evidence, sources)
        existing = await self._latest_snapshot(business, project_id, input_hash)
        if existing:
            return existing
        snapshot = ResearchIntelligenceSnapshot(
            organization_id=business.organization_id,
            business_id=business.id,
            research_project_id=project_id,
            intelligence_version=INTELLIGENCE_VERSION,
            input_hash=input_hash,
            source_count=len(sources),
            snapshot_count=len({row.id for row in source_snapshots}),
            evidence_count=len(evidence),
            finding_count=0,
            freshness=_overall_freshness(evidence),
            coverage_json=_coverage(evidence, sources),
            missing_areas_json=_missing_areas(evidence, sources),
        )
        self.session.add(snapshot)
        await self.session.flush()
        groups = _groups(
            evidence,
            sources,
            {snapshot.id: snapshot for snapshot in source_snapshots},
        )
        generated_findings = 0
        for group in groups:
            finding_projects = group["project_ids"] or ({project_id} if project_id else set())
            if not finding_projects:
                continue
            finding_ids = []
            for project_for_finding in sorted(finding_projects, key=str):
                finding = ResearchFinding(
                    organization_id=business.organization_id,
                    business_id=business.id,
                    research_project_id=project_for_finding,
                    category=_finding_category(group["category"]),
                    title=group["title"],
                    statement=group["statement"],
                    classification=_classification(group["evidence"]),
                    importance="medium",
                    evidence_strength=group["strength"],
                )
                self.session.add(finding)
                await self.session.flush()
                finding_ids.append(finding.id)
                for row in group["evidence"]:
                    await self.session.execute(
                        research_finding_evidence.insert().values(
                            finding_id=finding.id, evidence_id=row.id
                        )
                    )
            item = ResearchIntelligenceItem(
                organization_id=business.organization_id,
                business_id=business.id,
                snapshot_id=snapshot.id,
                research_project_id=project_id if project_id else None,
                competitor_id=group["competitor_id"],
                intelligence_type=group["intelligence_type"],
                category=group["category"],
                title=group["title"],
                statement=group["statement"],
                classification=_classification(group["evidence"]),
                strength=group["strength"],
                evidence_count=len(group["evidence"]),
                source_count=len({row.source_id for row in group["evidence"]}),
                freshness=_overall_freshness(group["evidence"]),
                metadata_json=_json_safe(
                    {
                        "independence": group["independence"],
                        "independent_source_count": group["independent_source_count"],
                        "source_ids": [str(row.source_id) for row in group["evidence"]],
                        "snapshot_ids": [
                            str(row.snapshot_id) for row in group["evidence"] if row.snapshot_id
                        ],
                        "pricing": _pricing_summary(group["evidence"]),
                    }
                ),
            )
            self.session.add(item)
            await self.session.flush()
            for finding_id in finding_ids:
                await self.session.execute(
                    research_intelligence_item_findings.insert().values(
                        item_id=item.id, finding_id=finding_id
                    )
                )
            generated_findings += len(finding_ids)
        snapshot.finding_count = generated_findings
        await self.session.commit()
        await self.session.refresh(snapshot)
        return snapshot

    async def get_snapshot(
        self, business: Business, snapshot_id: uuid.UUID
    ) -> ResearchIntelligenceSnapshot | None:
        return await self.session.scalar(
            select(ResearchIntelligenceSnapshot).where(
                ResearchIntelligenceSnapshot.id == snapshot_id,
                ResearchIntelligenceSnapshot.organization_id == business.organization_id,
                ResearchIntelligenceSnapshot.business_id == business.id,
            )
        )

    async def pricing_summary(
        self,
        business: Business,
        project_id: uuid.UUID | None = None,
        competitor_id: uuid.UUID | None = None,
    ) -> dict[str, Any]:
        evidence, sources, _ = await self._inputs(business, project_id)
        if competitor_id is not None:
            evidence = [
                row
                for row in evidence
                if sources.get(row.source_id)
                and sources[row.source_id].competitor_id == competitor_id
            ]
        return _pricing_summary([row for row in evidence if row.evidence_type == "pricing"])

    async def items(
        self,
        business: Business,
        snapshot: ResearchIntelligenceSnapshot,
        *,
        intelligence_type: str,
        project_id: uuid.UUID | None = None,
        competitor_id: uuid.UUID | None = None,
        category: str | None = None,
        classification: str | None = None,
        strength: str | None = None,
        freshness_value: str | None = None,
        source_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 100,
    ) -> list[ResearchIntelligenceItem]:
        where = [
            ResearchIntelligenceItem.organization_id == business.organization_id,
            ResearchIntelligenceItem.business_id == business.id,
            ResearchIntelligenceItem.snapshot_id == snapshot.id,
            ResearchIntelligenceItem.intelligence_type == intelligence_type,
        ]
        for column, value in (
            (ResearchIntelligenceItem.research_project_id, project_id),
            (ResearchIntelligenceItem.competitor_id, competitor_id),
            (ResearchIntelligenceItem.category, category),
            (ResearchIntelligenceItem.classification, classification),
            (ResearchIntelligenceItem.strength, strength),
            (ResearchIntelligenceItem.freshness, freshness_value),
        ):
            if value is not None:
                where.append(column == value)
        query = select(ResearchIntelligenceItem).where(*where)
        if source_type:
            query = query.where(
                ResearchIntelligenceItem.id.in_(
                    select(research_intelligence_item_findings.c.item_id)
                    .join(
                        research_finding_evidence,
                        research_finding_evidence.c.finding_id
                        == research_intelligence_item_findings.c.finding_id,
                    )
                    .join(
                        ResearchEvidence,
                        ResearchEvidence.id == research_finding_evidence.c.evidence_id,
                    )
                    .join(ResearchSource, ResearchSource.id == ResearchEvidence.source_id)
                    .where(ResearchSource.source_type == source_type)
                )
            )
        if date_from or date_to:
            evidence_query = (
                select(research_intelligence_item_findings.c.item_id)
                .join(
                    research_finding_evidence,
                    research_finding_evidence.c.finding_id
                    == research_intelligence_item_findings.c.finding_id,
                )
                .join(
                    ResearchEvidence, ResearchEvidence.id == research_finding_evidence.c.evidence_id
                )
            )
            if date_from:
                evidence_query = evidence_query.where(ResearchEvidence.captured_at >= date_from)
            if date_to:
                evidence_query = evidence_query.where(ResearchEvidence.captured_at <= date_to)
            query = query.where(ResearchIntelligenceItem.id.in_(evidence_query))
        return list(
            await self.session.scalars(
                query.order_by(desc(ResearchIntelligenceItem.created_at)).limit(limit)
            )
        )

    async def provenance(
        self, business: Business, item: ResearchIntelligenceItem
    ) -> list[dict[str, Any]]:
        rows = await self.session.execute(
            select(ResearchFinding, ResearchEvidence, ResearchSource, ResearchSourceSnapshot)
            .join(
                research_intelligence_item_findings,
                research_intelligence_item_findings.c.finding_id == ResearchFinding.id,
            )
            .join(
                research_finding_evidence,
                research_finding_evidence.c.finding_id == ResearchFinding.id,
            )
            .join(ResearchEvidence, ResearchEvidence.id == research_finding_evidence.c.evidence_id)
            .join(ResearchSource, ResearchSource.id == ResearchEvidence.source_id)
            .outerjoin(
                ResearchSourceSnapshot, ResearchSourceSnapshot.id == ResearchEvidence.snapshot_id
            )
            .where(
                research_intelligence_item_findings.c.item_id == item.id,
                ResearchFinding.organization_id == business.organization_id,
                ResearchFinding.business_id == business.id,
            )
        )
        return [
            {
                "finding_id": finding.id,
                "finding_title": finding.title,
                "evidence_id": evidence.id,
                "evidence_statement": evidence.statement,
                "source_id": source.id,
                "source_title": source.title,
                "source_url": source.url,
                "snapshot_id": snapshot.id if snapshot else evidence.snapshot_id,
                "captured_at": evidence.captured_at,
            }
            for finding, evidence, source, snapshot in rows
        ]


def _overall_freshness(rows: list[Any]) -> str:
    if not rows:
        return "unknown"
    values = {freshness(row.captured_at) for row in rows}
    if "stale" in values:
        return "stale"
    if "aging" in values:
        return "aging"
    return "fresh" if "fresh" in values else "unknown"


def _coverage(
    evidence: list[ResearchEvidence], sources: dict[uuid.UUID, ResearchSource]
) -> dict[str, Any]:
    customer_sources = {
        source.id for source in sources.values() if source.source_type in CUSTOMER_SOURCE_TYPES
    }
    competitor_sources = {
        source.id for source in sources.values() if source.competitor_id is not None
    }
    dimensions = {
        "market": any(row.evidence_type in _MARKET_CATEGORIES for row in evidence),
        "customer": any(row.source_id in customer_sources for row in evidence),
        "competitor": any(row.source_id in competitor_sources for row in evidence),
        "pricing": any(row.evidence_type == "pricing" for row in evidence),
        "offer": any(row.evidence_type == "offer" for row in evidence),
        "messaging": any(row.evidence_type == "messaging" for row in evidence),
        "product": any(row.evidence_type in {"product", "feature", "benefit"} for row in evidence),
        "reviews": any(row.evidence_type in {"review", "complaint"} for row in evidence),
        "trust": any(row.evidence_type == "trust_signal" for row in evidence),
    }
    covered = [key for key, value in dimensions.items() if value]
    return {"dimensions": dimensions, "covered": covered, "total": len(dimensions)}


def _missing_areas(
    evidence: list[ResearchEvidence], sources: dict[uuid.UUID, ResearchSource]
) -> list[dict[str, str]]:
    coverage = _coverage(evidence, sources)["dimensions"]
    labels = {
        "customer": ("No customer-originated evidence is available.", "high"),
        "pricing": ("No pricing evidence is available.", "medium"),
        "competitor": ("No competitor-linked evidence is available.", "high"),
        "offer": ("No offer evidence is available.", "medium"),
        "messaging": ("No messaging evidence is available.", "medium"),
        "trend": ("No market trend evidence is available.", "low"),
    }
    return [
        {"area": area, "reason": reason, "severity": severity}
        for area, (reason, severity) in labels.items()
        if not coverage.get(area, False)
    ]


def _groups(
    evidence: list[ResearchEvidence],
    sources: dict[uuid.UUID, ResearchSource],
    snapshots: dict[uuid.UUID, ResearchSourceSnapshot],
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[ResearchEvidence]] = defaultdict(list)
    for row in evidence:
        source = sources.get(row.source_id)
        if source is None:
            continue
        competitor_id = source.competitor_id
        source_type = source.source_type
        if source_type in CUSTOMER_SOURCE_TYPES and row.evidence_type in _CUSTOMER_CATEGORIES:
            intelligence_type = "customer"
            category = _category_for("customer", row.evidence_type)
        elif competitor_id:
            intelligence_type = "competitor"
            category = _category_for("competitor", row.evidence_type, competitor=True)
        else:
            intelligence_type = "market"
            category = _category_for("market", row.evidence_type)
        if not category:
            continue
        key = (
            intelligence_type,
            category,
            competitor_id,
            _normalize_statement(row.statement),
        )
        grouped[key].append(row)
    groups = []
    for (intelligence_type, category, competitor_id, _), rows in grouped.items():
        strength, independence, independent_count = _strength(
            rows,
            sources,
            snapshots,
            customer=intelligence_type == "customer",
        )
        groups.append(
            {
                "intelligence_type": intelligence_type,
                "category": category,
                "competitor_id": competitor_id,
                "project_ids": {
                    row.research_project_id for row in rows if row.research_project_id is not None
                },
                "title": f"{category.replace('_', ' ').title()} signal",
                "statement": rows[0].statement,
                "evidence": rows,
                "strength": strength,
                "independence": independence,
                "independent_source_count": independent_count,
            }
        )
    return groups


def _finding_category(category: str) -> str:
    return {
        "pain_point": "customer",
        "desire": "customer",
        "objection": "customer",
        "buying_trigger": "customer",
        "trust_factor": "customer",
        "benefit": "offer",
        "trend": "market",
        "problem": "market",
        "need": "market",
        "gap": "competitor",
        "pricing": "pricing",
        "offer": "offer",
        "positioning": "positioning",
        "messaging": "messaging",
        "product": "product",
        "feature": "product",
        "creative_pattern": "creative",
        "trust_signal": "competitor",
        "social_proof": "competitor",
        "complaint": "customer",
    }.get(category, "market")


def _pricing_summary(rows: list[ResearchEvidence]) -> dict[str, Any]:
    by_currency: dict[str, list[Decimal]] = defaultdict(list)
    discounts: list[str] = []
    bundles: list[str] = []
    shipping: list[str] = []
    for row in rows:
        parsed = _price(row.structured_value)
        if parsed:
            by_currency[parsed[0]].append(parsed[1])
        text = row.statement
        if re.search(r"(?i)\b\d+%\s*(off|discount)", text):
            discounts.append(text)
        if re.search(r"(?i)\bbuy\s+\d+\s+get\s+\d+", text):
            bundles.append(text)
        if re.search(r"(?i)free shipping|shipping over|shipping above", text):
            shipping.append(text)
    result: dict[str, Any] = {
        "currencies": {},
        "discount_patterns": discounts,
        "bundle_patterns": bundles,
        "shipping_thresholds": shipping,
    }
    for currency, values in sorted(by_currency.items()):
        ordered = sorted(values)
        median = None
        if len(ordered) >= 3:
            middle = len(ordered) // 2
            median = (
                ordered[middle] if len(ordered) % 2 else (ordered[middle - 1] + ordered[middle]) / 2
            )
        result["currencies"][currency] = {
            "observation_count": len(ordered),
            "minimum": str(ordered[0]),
            "maximum": str(ordered[-1]),
            "median": str(median) if median is not None else None,
            "common_price_points": [
                str(value) for value in sorted(set(ordered)) if ordered.count(value) >= 2
            ],
        }
    return result
