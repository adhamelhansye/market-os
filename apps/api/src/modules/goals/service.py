"""Goal service. Periods are half-open [period_start, period_end) and must
not overlap other goals of the same business (checked here, since no DB
exclusion constraint is practical without an extension)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError
from src.db.models import BusinessGoal
from src.modules.goals.schemas import GoalCreate, GoalUpdate
from src.modules.products.service import periods_overlap


async def list_goals_for_business(
    session: AsyncSession, business_id: uuid.UUID
) -> list[BusinessGoal]:
    return list(
        await session.scalars(
            select(BusinessGoal)
            .where(BusinessGoal.business_id == business_id)
            .order_by(BusinessGoal.period_start.desc())
        )
    )


async def create_goal(
    session: AsyncSession, business_id: uuid.UUID, payload: GoalCreate
) -> BusinessGoal:
    await _assert_no_overlap(session, business_id, payload.period_start, payload.period_end)
    goal = BusinessGoal(
        business_id=business_id,
        period_start=payload.period_start,
        period_end=payload.period_end,
        target_revenue=payload.target_revenue,
        target_profit=payload.target_profit,
        ad_budget=payload.ad_budget,
        maximum_cpa=payload.maximum_cpa,
        target_roas=payload.target_roas,
        currency=payload.currency,
    )
    session.add(goal)
    await session.commit()
    await session.refresh(goal)
    return goal


async def update_goal(
    session: AsyncSession, goal: BusinessGoal, payload: GoalUpdate
) -> BusinessGoal:
    changes = payload.model_dump(exclude_unset=True)
    period_start = changes.get("period_start", goal.period_start)
    period_end = changes.get("period_end", goal.period_end)
    await _assert_no_overlap(
        session, goal.business_id, period_start, period_end, exclude=goal.id
    )
    for field, value in changes.items():
        setattr(goal, field, value)
    await session.commit()
    await session.refresh(goal)
    return goal


async def delete_goal(session: AsyncSession, goal: BusinessGoal) -> None:
    await session.delete(goal)
    await session.commit()


async def _assert_no_overlap(
    session: AsyncSession,
    business_id: uuid.UUID,
    period_start,
    period_end,
    exclude: uuid.UUID | None = None,
) -> None:
    existing = list(
        await session.scalars(
            select(BusinessGoal).where(BusinessGoal.business_id == business_id)
        )
    )
    for goal in existing:
        if exclude is not None and goal.id == exclude:
            continue
        if periods_overlap(
            goal.period_start, goal.period_end, period_start, period_end
        ):
            raise ConflictError("Goal period overlaps an existing goal period")