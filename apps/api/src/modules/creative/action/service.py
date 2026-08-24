"""Creative action preparation service (Phase 8G).

Consumes ACKNOWLEDGED Phase 8F decision items and the latest 8F plan
payload, translates them deterministically (pure engine), and persists
Phase 8B CreativeTest drafts (status permanently ``draft``) plus
linkage rows for idempotency and second-stage review.

No LLM, no asset generation, no campaign/provider mutations, no
execution paths. Acknowledging a draft records second-stage review and
nothing else.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy.exc as sa_exc
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.db.models import Business
from src.db.models.creative import (
    CreativeConcept,
    CreativeTest,
)
from src.db.models.creative_action import (
    CreativeActionDraft,
    CreativeTestActivation,
)
from src.db.models.creative_decision import CreativeDecisionItemReview
from src.modules.creative.action import engine as action_engine
from src.modules.creative.decision.engine import REVIEW_STATE_ACKNOWLEDGED
from src.modules.creative.performance.engine import to_jsonable

NO_SNAPSHOT_STATUS = "no_snapshot"

# Categories that never translate into drafts (approved boundary).
EXCLUDED_CATEGORIES = ("investigation", "alignment")


async def _acknowledged_items(
    session: AsyncSession,
    *,
    business_id: uuid.UUID,
    plan_payload: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Acknowledged reviews mapped onto latest-plan items + orphans.

    Returns (acknowledged_items, orphaned) where orphaned acknowledgments
    reference opportunities absent from the latest plan (reported, never
    fabricated into drafts).
    """
    items_by_id = {
        str(item.get("opportunity_id")): item
        for item in plan_payload.get("items") or []
    }
    reviews = (
        await session.execute(
            select(CreativeDecisionItemReview).where(
                CreativeDecisionItemReview.business_id == business_id,
                CreativeDecisionItemReview.review_state == REVIEW_STATE_ACKNOWLEDGED,
            )
        )
    ).scalars().all()

    acknowledged: list[dict[str, Any]] = []
    orphaned: list[dict[str, Any]] = []
    for review in reviews:
        item = items_by_id.get(review.opportunity_id)
        if item is None:
            orphaned.append(
                {
                    "opportunity_id": review.opportunity_id,
                    "reason_code": "stale_reference",
                    "reason": "opportunity absent from the latest decision plan",
                }
            )
            continue
        acknowledged.append(item)
    acknowledged.sort(key=lambda i: str(i["opportunity_id"]))
    return acknowledged, orphaned


async def _concept_contexts(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    entity_ids: set[str],
) -> dict[str, dict[str, Any]]:
    """Contexts for supporting entity ids that resolve to concepts."""
    contexts: dict[str, dict[str, Any]] = {}
    if not entity_ids:
        return contexts
    ids = {uuid.UUID(e) for e in entity_ids if _is_uuid(e)}
    if not ids:
        return contexts
    concepts = (
        await session.execute(
            select(CreativeConcept).where(
                CreativeConcept.organization_id == organization_id,
                CreativeConcept.business_id == business_id,
                CreativeConcept.id.in_(ids),
            )
        )
    ).scalars().all()
    for concept in concepts:
        contexts[str(concept.id)] = {
            "funnel_stage": concept.funnel_stage,
            "angle": concept.angle,
            "hook_direction": concept.hook_direction,
            "creative_format": concept.creative_format,
            "message": concept.message,
            "offer_reference": str(concept.offer_reference) if concept.offer_reference else None,
            "messaging_reference": (
                str(concept.messaging_reference) if concept.messaging_reference else None
            ),
            "positioning_reference": (
                str(concept.positioning_reference) if concept.positioning_reference else None
            ),
            "provenance_chain": None,
        }
    return contexts


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(str(value))
        return True
    except (ValueError, TypeError):
        return False


# ---------------------------------------------------------------------------
# Generate
# ---------------------------------------------------------------------------


async def generate(
    session: AsyncSession,
    business: Business,
    *,
    created_by: uuid.UUID | None,
) -> dict[str, Any]:
    """Translate acknowledged items into 8B test drafts (idempotent)."""
    from src.modules.creative.decision.service import latest_plan

    plan_row = await latest_plan(
        session, organization_id=business.organization_id, business_id=business.id
    )
    if plan_row is None:
        return {
            "report": action_engine.empty_report(),
            "snapshot_ids": [],
            "created_count": 0,
            "orphaned": [],
        }

    plan_payload = plan_row.payload or {}
    acknowledged, orphaned = await _acknowledged_items(
        session, business_id=business.id, plan_payload=plan_payload
    )

    # Contexts: supporting entities first; full in-scope concept set as the
    # deterministic fallback source for non-varied draft dimensions.
    all_concepts = (
        (
            await session.execute(
                select(CreativeConcept).where(
                    CreativeConcept.organization_id == business.organization_id,
                    CreativeConcept.business_id == business.id,
                )
            )
        )
        .scalars()
        .all()
    )
    all_concept_contexts = {
        str(concept.id): {
            "funnel_stage": concept.funnel_stage,
            "angle": concept.angle,
            "hook_direction": concept.hook_direction,
            "creative_format": concept.creative_format,
            "message": concept.message,
            "offer_reference": (
                str(concept.offer_reference) if concept.offer_reference else None
            ),
            "messaging_reference": (
                str(concept.messaging_reference) if concept.messaging_reference else None
            ),
            "positioning_reference": (
                str(concept.positioning_reference)
                if concept.positioning_reference
                else None
            ),
            "provenance_chain": None,
        }
        for concept in all_concepts
    }
    supporting_ids: set[str] = set()
    for item in acknowledged:
        supporting_ids.update(str(x) for x in item.get("supporting_entity_ids", []))
    supporting_contexts = {
        entity_id: ctx
        for entity_id, ctx in all_concept_contexts.items()
        if entity_id in supporting_ids
    }

    report = action_engine.build_action_report(
        acknowledged_items=acknowledged,
        concept_contexts=supporting_contexts,
        business_id=str(business.id),
        source_plan_fingerprint=plan_row.fingerprint,
        scope_contexts=all_concept_contexts,
    )

    snapshot_ids: list[uuid.UUID] = []
    created_count = 0
    for draft in report["drafts"]:
        linkage, created = await _persist_draft(
            session,
            business=business,
            draft=draft,
            created_by=created_by,
        )
        snapshot_ids.append(linkage.id)
        if created:
            created_count += 1
    await session.commit()
    report["summary"]["drafts_persisted"] = len(snapshot_ids)
    report["summary"]["drafts_created"] = created_count
    return {
        "report": report,
        "snapshot_ids": snapshot_ids,
        "created_count": created_count,
        "orphaned": orphaned,
    }


async def _persist_draft(
    session: AsyncSession,
    *,
    business: Business,
    draft: dict[str, Any],
    created_by: uuid.UUID | None,
) -> tuple[CreativeActionDraft, bool]:
    """Create the 8B CreativeTest draft row + linkage row (idempotent).

    The CreativeTest is ALWAYS created with status="draft" and no code
    path here ever changes it.
    """
    existing = (
        await session.execute(
            select(CreativeActionDraft).where(
                CreativeActionDraft.business_id == business.id,
                CreativeActionDraft.source_opportunity_id
                == draft["source_opportunity_id"],
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, False

    spec = draft.get("spec") or {}
    test = CreativeTest(
        organization_id=business.organization_id,
        business_id=business.id,
        test_id=draft["draft_test_id"],
        name=draft["draft_name"],
        objective=spec.get("objective") or "awareness",
        test_variable=draft.get("test_variable") or "angle",
        control_variables={
            k: v
            for k, v in spec.items()
            if k not in (draft.get("test_variable") or "",)
        },
        variants=list(draft.get("variants") or []),
        hypothesis=draft.get("hypothesis") or "",
        based_on=f"acknowledged opportunity {draft['source_opportunity_id']}",
        success_metric=spec.get("success_metric"),
        status="draft",
    )
    session.add(test)
    try:
        await session.flush()
    except sa_exc.IntegrityError as exc:
        raise ConflictError("draft test id already exists") from exc

    linkage = CreativeActionDraft(
        organization_id=business.organization_id,
        business_id=business.id,
        source_opportunity_id=draft["source_opportunity_id"],
        source_plan_fingerprint=draft["source_plan_fingerprint"],
        draft_test_id=test.test_id,
        draft_kind=draft["kind"],
        review_state="proposed",
        payload=to_jsonable({**draft, "creative_test_row_id": str(test.id)}),
        created_by=created_by,
    )
    session.add(linkage)
    try:
        await session.flush()
    except sa_exc.IntegrityError as exc:
        raise ConflictError("action draft already exists for this opportunity") from exc
    return linkage, True


# ---------------------------------------------------------------------------
# Second-stage review (same four non-executional states)
# ---------------------------------------------------------------------------


async def review_draft(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    draft_id: uuid.UUID,
    review_state: str,
    note: str | None,
    decided_by: uuid.UUID | None,
) -> CreativeActionDraft:
    """Record second-stage human review of a DRAFT. Nothing executes."""
    from src.modules.creative.decision.engine import ALLOWED_REVIEW_STATES

    if review_state not in ALLOWED_REVIEW_STATES:
        raise ConflictError(
            f"review_state must be one of {', '.join(ALLOWED_REVIEW_STATES)}"
        )
    draft_row = (
        await session.execute(
            select(CreativeActionDraft).where(
                CreativeActionDraft.id == draft_id,
                CreativeActionDraft.organization_id == organization_id,
                CreativeActionDraft.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if draft_row is None:
        raise NotFoundError("Action draft not found")

    # NOTE: no code path in Phase 8G ever writes CreativeTest.status;
    # the underlying draft therefore cannot leave "draft" via review.
    draft_row.review_state = review_state
    draft_row.note = note
    draft_row.decided_by = decided_by
    await session.commit()
    return draft_row


# ---------------------------------------------------------------------------
# Reads
# ---------------------------------------------------------------------------


async def list_drafts(
    session: AsyncSession, *, organization_id: uuid.UUID, business_id: uuid.UUID
) -> list[CreativeActionDraft]:
    rows = (
        (
            await session.execute(
                select(CreativeActionDraft)
                .where(
                    CreativeActionDraft.organization_id == organization_id,
                    CreativeActionDraft.business_id == business_id,
                )
                .order_by(CreativeActionDraft.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


__all__ = [
    "NO_SNAPSHOT_STATUS",
    "generate",
    "review_draft",
    "list_drafts",
]


# ---------------------------------------------------------------------------
# Lifecycle tracking (Phase 8H) - bounded state machine over 8G drafts
# ---------------------------------------------------------------------------

LIFECYCLE_TRANSITIONS: dict[str, dict[str, str | None]] = {
    # from -> {to: requirement}
    "draft": {
        "active": "acknowledged_review",
    },
    "active": {"completed": None, "cancelled": None},
    "completed": {},
    "cancelled": {},
}

ACTIVATION_REQUIRED_REVIEW_STATE = "acknowledged"


async def activate_draft(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    draft_id: uuid.UUID,
    actor_id: uuid.UUID,
    actor_role: str,
) -> tuple[CreativeActionDraft, Any]:
    """Activate an acknowledged 8G draft (draft -> active).

    Strict gates, each failing explicitly:
      - actor role must be owner or admin
      - the draft's second-stage review must be exactly ``acknowledged``
        (proposed/dismissed/deferred are never implicitly executable)
      - the CreativeTest must currently be ``status = 'draft'``
      - a test may be activated at most once

    Records an immutable activation event with full provenance. No
    provider calls, no campaign mutations, no scheduling.
    """
    draft_row = (
        await session.execute(
            select(CreativeActionDraft).where(
                CreativeActionDraft.id == draft_id,
                CreativeActionDraft.organization_id == organization_id,
                CreativeActionDraft.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if draft_row is None:
        raise NotFoundError("Action draft not found")

    if draft_row.review_state != ACTIVATION_REQUIRED_REVIEW_STATE:
        raise ConflictError(
            f"activation requires second-stage review_state="
            f"'{ACTIVATION_REQUIRED_REVIEW_STATE}'; current state is "
            f"'{draft_row.review_state}'"
        )

    prior_event = (
        await session.execute(
            select(CreativeTestActivation).where(
                CreativeTestActivation.business_id == business_id,
                CreativeTestActivation.creative_test_external_ref
                == draft_row.draft_test_id,
            )
        )
    ).scalar_one_or_none()
    if prior_event is not None:
        raise ConflictError(
            "creative test has already been activated; lifecycle is "
            "single-activation"
        )

    test = (
        await session.execute(
            select(CreativeTest).where(CreativeTest.test_id == draft_row.draft_test_id)
        )
    ).scalar_one_or_none()
    if test is None:
        raise NotFoundError("Underlying creative test draft not found")
    if test.status != "draft":
        raise ConflictError(
            f"activation requires CreativeTest status='draft'; "
            f"current status is '{test.status}'"
        )

    previous_status = test.status
    test.status = "active"

    event = CreativeTestActivation(
        organization_id=organization_id,
        business_id=business_id,
        creative_test_id=test.id,
        creative_test_external_ref=test.test_id,
        source_action_draft_id=draft_row.id,
        source_opportunity_id=draft_row.source_opportunity_id,
        source_plan_fingerprint=draft_row.source_plan_fingerprint,
        previous_status=previous_status,
        new_status="active",
        activated_by=actor_id,
    )
    session.add(event)
    try:
        await session.flush()
    except sa_exc.IntegrityError as exc:
        raise ConflictError("activation event conflict") from exc
    await session.commit()
    return draft_row, event


async def transition_lifecycle(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    test_external_ref: str,
    target_status: str,
    actor_id: uuid.UUID,
    actor_role: str,
) -> Any:
    """Apply a bounded lifecycle transition (active -> completed/cancelled).

    Direct transitions from any other state are rejected; every accepted
    transition records an immutable event.
    """
    if target_status not in ("completed", "cancelled"):
        raise ConflictError(
            "target_status must be 'completed' or 'cancelled'"
        )

    test = (
        await session.execute(
            select(CreativeTest).where(
                CreativeTest.test_id == test_external_ref,
                CreativeTest.organization_id == organization_id,
                CreativeTest.business_id == business_id,
            )
        )
    ).scalar_one_or_none()
    if test is None:
        raise NotFoundError("Creative test not found")

    allowed_targets = LIFECYCLE_TRANSITIONS.get(test.status, {})
    if target_status not in allowed_targets:
        raise ConflictError(
            f"transition '{test.status}' -> '{target_status}' is not part of "
            "the bounded lifecycle"
        )

    # The active->completed/cancelled transition does not require a review
    # state change; it closes the internal testing lifecycle.
    previous_status = test.status
    test.status = target_status

    # Provenance: locate the originating activation for linkage fields.
    activation = (
        await session.execute(
            select(CreativeTestActivation)
            .where(
                CreativeTestActivation.business_id == business_id,
                CreativeTestActivation.creative_test_external_ref == test_external_ref,
                CreativeTestActivation.new_status == "active",
            )
            .order_by(CreativeTestActivation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    event = CreativeTestActivation(
        organization_id=organization_id,
        business_id=business_id,
        creative_test_id=test.id,
        creative_test_external_ref=test.test_id,
        source_action_draft_id=(
            activation.source_action_draft_id if activation else test.id
        ),
        source_opportunity_id=(
            activation.source_opportunity_id if activation else "unknown"
        ),
        source_plan_fingerprint=(
            activation.source_plan_fingerprint if activation else "unknown"
        ),
        previous_status=previous_status,
        new_status=target_status,
        activated_by=actor_id,
    )
    session.add(event)
    await session.commit()
    return event


async def lifecycle_events(
    session: AsyncSession,
    *,
    organization_id: uuid.UUID,
    business_id: uuid.UUID,
    test_external_ref: str | None = None,
) -> list[Any]:
    """Immutable lifecycle history, newest first."""
    conditions = [
        CreativeTestActivation.organization_id == organization_id,
        CreativeTestActivation.business_id == business_id,
    ]
    if test_external_ref:
        conditions.append(
            CreativeTestActivation.creative_test_external_ref == test_external_ref
        )
    rows = (
        (
            await session.execute(
                select(CreativeTestActivation)
                .where(*conditions)
                .order_by(CreativeTestActivation.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


__all__.extend(["activate_draft", "transition_lifecycle", "lifecycle_events"])
