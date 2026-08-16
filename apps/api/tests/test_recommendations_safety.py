"""Recommendations safety tests (Phase 4B, spec §40).

The decision engine must NEVER execute an action: no provider mutation, no
budget change, no campaign edit, no sync trigger, no webhook emit. This test
file enforces that in two ways:

1. Static import graph: `src.modules.recommendations` may only depend on
   deterministic internal services (metrics/diagnostics/forecasting/
   economics/goals). It must not import the integration adapters or the
   sync/jobs layer, so there is no code path to a mutation.

2. Behavioral state test: running the full generate pipeline over a seeded
   tenant leaves provider-side state untouched (no sync runs, no webhook
   events, no connection changes) — only the idempotent recommendations
   rows are written.
"""

import re
from pathlib import Path

from conftest import create_tenant
from httpx import AsyncClient
from sqlalchemy import func, select
from test_metrics import _seed_standard_tenant

from src.db.models import (
    IntegrationConnection,
    IntegrationCredential,
    Recommendation,
    SyncRun,
    WebhookEvent,
)

MODULE_DIR = Path(__file__).resolve().parents[1] / "src" / "modules" / "recommendations"

GENERATE_URL = "/api/v1/businesses/{business_id}/recommendations/generate"
LIST_URL = "/api/v1/businesses/{business_id}/recommendations"


# ---------------------------------------------------------------------------
# Static import graph: no provider/sync/jobs dependency
# ---------------------------------------------------------------------------


def test_import_graph_has_no_mutation_dependency() -> None:
    """The module can only compute decisions from deterministic services."""
    sources = [p for p in MODULE_DIR.iterdir() if p.suffix == ".py"]
    assert sources, "recommendations module source files must exist"

    forbidden: list[str] = []
    for source in sources:
        text = source.read_text(encoding="utf-8")
        for match in re.finditer(r"^(?:from|import)\s+([\w.]+)", text, re.MULTILINE):
            top = match.group(1).split(".")[0]
            if top == "src":
                full = match.group(1)
                if full.startswith("src.modules.integrations"):
                    forbidden.append(f"{source.name}: imports {full}")
                if full.startswith("src.modules.sync"):
                    forbidden.append(f"{source.name}: imports {full}")
                if full.startswith("src.jobs") or full.startswith("src.modules.jobs"):
                    forbidden.append(f"{source.name}: imports {full}")
    assert not forbidden, (
        "recommendations must never import provider/sync/jobs code:\n"
        + "\n".join(forbidden)
    )


def test_source_has_no_action_verbs() -> None:
    """Decision/review code must never contain action keywords."""
    action_words = (
        "pause_campaign",
        "resume_campaign",
        "delete_campaign",
        "create_campaign",
        "update_campaign",
        "set_budget",
        "increase_budget",
        "decrease_budget",
        "change_bid",
        "perform_bulk_operation",
        "post_to_provider",
        "send_webhook",
    )
    offenders: list[str] = []
    for source in MODULE_DIR.iterdir():
        if source.suffix != ".py":
            continue
        text = source.read_text(encoding="utf-8")
        for word in action_words:
            if word in text:
                offenders.append(f"{source.name}: contains '{word}'")
    assert not offenders, "action verbs must never appear in recommendation code:\n" + "\n".join(
        offenders
    )


def test_decision_types_are_all_review_labels() -> None:
    """Every decision type is a review label — none implies execution."""
    from src.modules.recommendations.severity import DECISION_TYPES

    assert DECISION_TYPES == (
        "tracking_issue",
        "data_quality_issue",
        "insufficient_data",
        "learning",
        "kill_review",
        "scale_review",
        "optimize",
        "maintain",
    )
    # NEVER an autonomous kill: the only kill-adjacent label is a human
    # review marker, and no type name alone implies execution.
    assert "kill" not in (t for t in DECISION_TYPES if t != "kill_review")
    assert all(
        "review" in t
        for t in DECISION_TYPES
        if t in ("kill_review", "scale_review")
    )


# ---------------------------------------------------------------------------
# Behavioral: generate leaves provider state untouched
# ---------------------------------------------------------------------------


async def _counts(session) -> dict:
    async def _count(model) -> int:
        return (await session.execute(select(func.count(model.id)))).scalar_one()

    return {
        "sync_runs": await _count(SyncRun),
        "webhook_events": await _count(WebhookEvent),
        "recommendations": await _count(Recommendation),
        "connections": await _count(IntegrationConnection),
        "credentials": await _count(IntegrationCredential),
    }


async def test_generate_touches_only_recommendations_rows(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)

    before = await _counts(session)
    assert before["sync_runs"] == 0
    assert before["webhook_events"] == 0
    assert before["connections"] == 1  # the seeded Meta connection
    assert before["credentials"] == 1
    assert before["recommendations"] == 0

    response = await client.post(
        GENERATE_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        json={},
    )
    assert response.status_code == 200, response.text

    after = await _counts(session)
    # Only the decisions themselves are persisted
    assert after["sync_runs"] == before["sync_runs"] == 0
    assert after["webhook_events"] == before["webhook_events"] == 0
    assert after["connections"] == before["connections"]
    assert after["credentials"] == before["credentials"]
    assert after["recommendations"] == 3


async def test_list_never_touches_provider_state(client: AsyncClient, session) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)

    before = await _counts(session)
    response = await client.get(
        LIST_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
    )
    assert response.status_code == 200, response.text

    after = await _counts(session)
    # Reading recommendations is side-effect free for providers/sync state.
    # The list endpoint may persist its own deterministic cache rows
    # (idempotent fingerprint upsert) but never touches provider state.
    assert after["sync_runs"] == before["sync_runs"] == 0
    assert after["webhook_events"] == before["webhook_events"] == 0
    assert after["connections"] == before["connections"]
    assert after["credentials"] == before["credentials"]


async def test_recommendation_payloads_contain_no_action_keys(
    client: AsyncClient, session
) -> None:
    tenant = await create_tenant(session)
    await _seed_standard_tenant(session, tenant)

    response = await client.post(
        GENERATE_URL.format(business_id=tenant["business"].id),
        headers=tenant["headers"],
        json={},
    )
    assert response.status_code == 200, response.text
    payload = response.text

    for key in (
        '"action"',
        '"execute"',
        '"pause"',
        '"operation"',
        '"webhook"',
    ):
        assert key not in payload, f"response must not contain {key}"
    assert '"review_suggestions"' in payload
    assert all(
        f'"{label}"' in payload
        for label in ("tracking_issue", "scale_review", "kill_review", "maintain")
    )