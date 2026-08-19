from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from src.core.dependencies import CurrentBusinessId, DbSession, SettingsDep, require_permission
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.modules.businesses.service import get_business
from src.modules.strategy import decision as decision_service
from src.modules.strategy import messaging as messaging_service
from src.modules.strategy import service
from src.modules.strategy.schemas import (
    MessagingGenerateRequest,
    MessagingProvenanceResponse,
    MessagingStrategyRead,
    MessagingVersionsResponse,
    OfferCandidateCreate,
    OfferCandidateRead,
    OfferResponse,
    OfferValidateRequest,
    OfferVersionsResponse,
    PositioningCandidateCreate,
    PositioningCandidateRead,
    PositioningResponse,
    PositioningVersionsResponse,
    StrategyDecisionEvaluateRequest,
    StrategyDecisionListResponse,
    StrategyDecisionProvenanceResponse,
    StrategyDecisionRead,
    StrategySnapshotResponse,
    StrategySummaryResponse,
)

router = APIRouter(tags=["strategy"])


def _positioning(data: dict) -> PositioningResponse:
    data["candidates"] = [
        PositioningCandidateRead.model_validate(candidate) for candidate in data["candidates"]
    ]
    return PositioningResponse.model_validate(data)


def _offers(data: dict) -> OfferResponse:
    data["candidates"] = [
        OfferCandidateRead.model_validate(candidate) for candidate in data["candidates"]
    ]
    return OfferResponse.model_validate(data)


def _decision(row) -> StrategyDecisionRead:
    return StrategyDecisionRead.model_validate(
        {
            "id": row.id,
            "candidate_type": row.candidate_type,
            "candidate_id": row.candidate_id,
            "strategy_version": row.strategy_version,
            "decision_rules_version": row.decision_rules_version,
            "status": row.status,
            "overall_score": row.overall_score,
            "input_snapshot": row.input_snapshot,
            "evaluation": row.evaluation,
            "reasons": row.reasons,
            "provenance": row.provenance,
            "created_at": row.created_at,
        }
    )


async def _messaging(session: DbSession, row) -> MessagingStrategyRead:
    components = await messaging_service.components(session, row)
    angles = await messaging_service.angles(session, row)
    return MessagingStrategyRead.model_validate(
        {
            "id": row.id,
            "version": row.version,
            "messaging_version": row.messaging_version,
            "status": row.status,
            "positioning_candidate_id": row.positioning_candidate_id,
            "offer_candidate_id": row.offer_candidate_id,
            "strategy_decision_id": row.strategy_decision_id,
            "input_snapshot": row.input_snapshot,
            "core_message": row.core_message,
            "quality": row.quality,
            "components": [
                {
                    "id": item.id,
                    "component_type": item.component_type,
                    "statement": item.statement,
                    "classification": item.classification,
                    "strength": item.strength,
                    "claim_status": item.claim_status,
                    "status": item.status,
                    "funnel_stage": item.funnel_stage,
                    "details": item.details,
                    "evidence_refs": item.evidence_refs,
                    "provenance": item.provenance,
                }
                for item in components
            ],
            "angles": [
                {
                    "id": item.id,
                    "name": item.name,
                    "angle_type": item.angle_type,
                    "core_message": item.core_message,
                    "hook_direction": item.hook_direction,
                    "supporting_points": item.supporting_points,
                    "cta_type": item.cta_type,
                    "funnel_stage": item.funnel_stage,
                    "strength": item.strength,
                    "status": item.status,
                    "evidence_refs": item.evidence_refs,
                }
                for item in angles
            ],
            "created_at": row.created_at,
        }
    )


@router.get("/businesses/{business_id}/strategy/positioning", response_model=PositioningResponse)
async def get_positioning(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> PositioningResponse:
    return _positioning(
        await service.positioning_response(session, await get_business(session, business_id))
    )


@router.post(
    "/businesses/{business_id}/strategy/positioning/candidate",
    response_model=PositioningCandidateRead,
    status_code=201,
)
@router.post(
    "/businesses/{business_id}/strategy/positioning/candidates",
    response_model=PositioningCandidateRead,
    status_code=201,
)
async def create_positioning_candidate(
    payload: PositioningCandidateCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> PositioningCandidateRead:
    business = await get_business(session, business_id)
    candidate = await service.create_positioning_candidate(session, business, payload)
    strategy = await session.get(service.PositioningStrategy, candidate.positioning_strategy_id)
    return PositioningCandidateRead.model_validate(
        {
            **{
                column.name: getattr(candidate, column.name)
                for column in candidate.__table__.columns
            },
            "strategy_version": strategy.strategy_version
            if strategy
            else service.POSITIONING_VERSION,
        }
    )


@router.get(
    "/businesses/{business_id}/strategy/positioning/candidate/{candidate_id}",
    response_model=PositioningCandidateRead,
)
@router.get(
    "/businesses/{business_id}/strategy/positioning/candidates/{candidate_id}",
    response_model=PositioningCandidateRead,
)
async def get_positioning_candidate(
    business_id: CurrentBusinessId,
    candidate_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> PositioningCandidateRead:
    business = await get_business(session, business_id)
    candidate = await service.get_positioning_candidate(session, business, candidate_id)
    strategy = await session.get(service.PositioningStrategy, candidate.positioning_strategy_id)
    return PositioningCandidateRead.model_validate(
        {
            **{
                column.name: getattr(candidate, column.name)
                for column in candidate.__table__.columns
            },
            "strategy_version": strategy.strategy_version
            if strategy
            else service.POSITIONING_VERSION,
        }
    )


@router.post(
    "/businesses/{business_id}/strategy/positioning/recommend", response_model=PositioningResponse
)
async def recommend_positioning(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> PositioningResponse:
    return _positioning(
        await service.recommend_positioning(session, await get_business(session, business_id))
    )


@router.get(
    "/businesses/{business_id}/strategy/positioning/versions",
    response_model=PositioningVersionsResponse,
)
async def get_positioning_versions(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> PositioningVersionsResponse:
    business = await get_business(session, business_id)
    return PositioningVersionsResponse(
        versions=[
            _positioning(row) for row in await service.positioning_versions(session, business)
        ]
    )


@router.get("/businesses/{business_id}/strategy/offers", response_model=OfferResponse)
async def get_offers(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
    product_id: Annotated[uuid.UUID | None, Query()] = None,
) -> OfferResponse:
    data = await service.offer_response(session, await get_business(session, business_id))
    if product_id is not None:
        data["candidates"] = [
            candidate for candidate in data["candidates"] if candidate["product_id"] == product_id
        ]
    return _offers(data)


@router.post(
    "/businesses/{business_id}/strategy/offers/candidate",
    response_model=OfferCandidateRead,
    status_code=201,
)
@router.post(
    "/businesses/{business_id}/strategy/offers/candidates",
    response_model=OfferCandidateRead,
    status_code=201,
)
async def create_offer_candidate(
    payload: OfferCandidateCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> OfferCandidateRead:
    business = await get_business(session, business_id)
    candidate = await service.create_offer_candidate(session, business, payload)
    strategy = await session.get(service.OfferStrategy, candidate.offer_strategy_id)
    return OfferCandidateRead.model_validate(
        {
            **{
                column.name: getattr(candidate, column.name)
                for column in candidate.__table__.columns
            },
            "strategy_version": strategy.strategy_version if strategy else service.OFFER_VERSION,
        }
    )


@router.get(
    "/businesses/{business_id}/strategy/offers/candidate/{candidate_id}",
    response_model=OfferCandidateRead,
)
@router.get(
    "/businesses/{business_id}/strategy/offers/candidates/{candidate_id}",
    response_model=OfferCandidateRead,
)
async def get_offer_candidate(
    business_id: CurrentBusinessId,
    candidate_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OfferCandidateRead:
    business = await get_business(session, business_id)
    candidate = await service.get_offer_candidate(session, business, candidate_id)
    strategy = await session.get(service.OfferStrategy, candidate.offer_strategy_id)
    return OfferCandidateRead.model_validate(
        {
            **{
                column.name: getattr(candidate, column.name)
                for column in candidate.__table__.columns
            },
            "strategy_version": strategy.strategy_version if strategy else service.OFFER_VERSION,
        }
    )


@router.post("/businesses/{business_id}/strategy/offers/validate", response_model=OfferResponse)
async def validate_offer(
    payload: OfferValidateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> OfferResponse:
    return _offers(
        await service.validate_offer(
            session, await get_business(session, business_id), payload.candidate_id
        )
    )


@router.post("/businesses/{business_id}/strategy/offers/recommend", response_model=OfferResponse)
async def recommend_offer(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> OfferResponse:
    return _offers(await service.recommend_offer(session, await get_business(session, business_id)))


@router.get(
    "/businesses/{business_id}/strategy/offers/versions",
    response_model=OfferVersionsResponse,
)
@router.get(
    "/businesses/{business_id}/strategy/offer-versions", response_model=OfferVersionsResponse
)
async def get_offer_versions(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> OfferVersionsResponse:
    business = await get_business(session, business_id)
    return OfferVersionsResponse(
        versions=[_offers(row) for row in await service.offer_versions(session, business)]
    )


@router.get("/businesses/{business_id}/strategy/summary", response_model=StrategySummaryResponse)
async def get_strategy_summary(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> StrategySummaryResponse:
    data = await service.strategy_summary(session, await get_business(session, business_id))
    data["positioning"] = _positioning(data["positioning"])
    data["offers"] = _offers(data["offers"])
    return StrategySummaryResponse.model_validate(data)


@router.get("/businesses/{business_id}/strategy/snapshot", response_model=StrategySnapshotResponse)
async def get_strategy_snapshot(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> StrategySnapshotResponse:
    snapshot = await service.latest_snapshot(session, await get_business(session, business_id))
    if snapshot is None:
        raise NotFoundError("Strategy snapshot not found")
    return StrategySnapshotResponse.model_validate(
        {
            "id": snapshot.id,
            "strategy_kind": snapshot.strategy_kind,
            "strategy_version": snapshot.strategy_version,
            "research_intelligence_version": snapshot.research_intelligence_version,
            "input_snapshot_refs": snapshot.input_snapshot_refs,
            "coverage": snapshot.coverage_json,
            "missing_research_areas": snapshot.missing_research_areas,
            "created_at": snapshot.created_at,
        }
    )


@router.get(
    "/businesses/{business_id}/strategy/decisions",
    response_model=StrategyDecisionListResponse,
)
async def list_strategy_decisions(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> StrategyDecisionListResponse:
    business = await get_business(session, business_id)
    return StrategyDecisionListResponse(
        decisions=[
            _decision(row) for row in await decision_service.list_decisions(session, business)
        ]
    )


@router.post(
    "/businesses/{business_id}/strategy/decisions/evaluate",
    response_model=StrategyDecisionRead,
    status_code=201,
)
async def evaluate_strategy_decision(
    payload: StrategyDecisionEvaluateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
    settings: SettingsDep,
) -> StrategyDecisionRead:
    business = await get_business(session, business_id)
    return _decision(await decision_service.evaluate_decision(session, business, payload, settings))


@router.get(
    "/businesses/{business_id}/strategy/decisions/{decision_id}/provenance",
    response_model=StrategyDecisionProvenanceResponse,
)
async def strategy_decision_provenance(
    business_id: CurrentBusinessId,
    decision_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> StrategyDecisionProvenanceResponse:
    business = await get_business(session, business_id)
    row = await decision_service.get_decision(session, business, decision_id)
    return StrategyDecisionProvenanceResponse(
        decision_id=row.id,
        candidate_type=row.candidate_type,
        candidate_id=row.candidate_id,
        provenance=row.provenance,
    )


@router.get(
    "/businesses/{business_id}/strategy/decisions/{decision_id}",
    response_model=StrategyDecisionRead,
)
async def get_strategy_decision(
    business_id: CurrentBusinessId,
    decision_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> StrategyDecisionRead:
    business = await get_business(session, business_id)
    return _decision(await decision_service.get_decision(session, business, decision_id))


@router.get("/businesses/{business_id}/strategy/messaging", response_model=MessagingStrategyRead)
async def get_messaging(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> MessagingStrategyRead:
    business = await get_business(session, business_id)
    row = await messaging_service.latest(session, business)
    if row is None:
        raise NotFoundError("Messaging strategy not found")
    return await _messaging(session, row)


@router.post(
    "/businesses/{business_id}/strategy/messaging/generate",
    response_model=MessagingStrategyRead,
    status_code=201,
)
async def generate_messaging(
    payload: MessagingGenerateRequest,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> MessagingStrategyRead:
    row = await messaging_service.generate(
        session, await get_business(session, business_id), payload
    )
    return await _messaging(session, row)


@router.get(
    "/businesses/{business_id}/strategy/messaging/versions",
    response_model=MessagingVersionsResponse,
)
async def messaging_versions(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> MessagingVersionsResponse:
    business = await get_business(session, business_id)
    return MessagingVersionsResponse(
        versions=[
            await _messaging(session, row)
            for row in await messaging_service.versions(session, business)
        ]
    )


@router.get(
    "/businesses/{business_id}/strategy/messaging/{messaging_id}",
    response_model=MessagingStrategyRead,
)
async def get_messaging_by_id(
    business_id: CurrentBusinessId,
    messaging_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> MessagingStrategyRead:
    return await _messaging(
        session,
        await messaging_service.get_strategy(
            session, await get_business(session, business_id), messaging_id
        ),
    )


@router.get(
    "/businesses/{business_id}/strategy/messaging/{messaging_id}/provenance",
    response_model=MessagingProvenanceResponse,
)
async def messaging_provenance(
    business_id: CurrentBusinessId,
    messaging_id: uuid.UUID,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> MessagingProvenanceResponse:
    row = await messaging_service.get_strategy(
        session, await get_business(session, business_id), messaging_id
    )
    components = await messaging_service.components(session, row)
    return MessagingProvenanceResponse(
        messaging_strategy_id=row.id,
        provenance=[entry for component in components for entry in component.provenance],
    )
