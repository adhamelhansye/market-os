"""Business goal endpoints, scoped to a business."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select

from src.core.dependencies import (
    CurrentBusinessId,
    DbSession,
    require_permission,
)
from src.core.exceptions import NotFoundError
from src.core.tenancy import TenantContext
from src.db.models import BusinessGoal
from src.modules.goals import service
from src.modules.goals.schemas import GoalCreate, GoalRead, GoalUpdate

router = APIRouter(tags=["goals"])


async def get_goal_from_path(
    request: Request, business_id: CurrentBusinessId, session: DbSession
) -> BusinessGoal:
    raw = request.path_params.get("goal_id", "")
    try:
        goal_id = uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Goal not found") from None
    goal = await session.get(BusinessGoal, goal_id)
    if goal is None or goal.business_id != business_id:
        raise NotFoundError("Goal not found")
    return goal


CurrentGoal = Annotated[BusinessGoal, Depends(get_goal_from_path)]


async def list_goals(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[GoalRead]:
    goals = list(
        await session.scalars(
            select(BusinessGoal)
            .where(BusinessGoal.business_id == business_id)
            .order_by(BusinessGoal.period_start.desc())
        )
    )
    return [GoalRead.model_validate(g) for g in goals]


@router.get("/businesses/{business_id}/goals", response_model=list[GoalRead])
async def get_goals(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[GoalRead]:
    return await list_goals(business_id, tenant, session)


@router.post(
    "/businesses/{business_id}/goals", response_model=GoalRead, status_code=201
)
async def create_goal(
    payload: GoalCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> GoalRead:
    goal = await service.create_goal(session, business_id, payload)
    return GoalRead.model_validate(goal)


@router.patch("/businesses/{business_id}/goals/{goal_id}", response_model=GoalRead)
async def update_goal(
    payload: GoalUpdate,
    goal: CurrentGoal,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> GoalRead:
    goal = await service.update_goal(session, goal, payload)
    return GoalRead.model_validate(goal)


@router.delete("/businesses/{business_id}/goals/{goal_id}", status_code=204)
async def delete_goal(
    goal: CurrentGoal,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> None:
    await service.delete_goal(session, goal)