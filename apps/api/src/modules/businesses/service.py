"""Business service: create/update businesses and their profile, plus
server-side onboarding completion validation."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import ConflictError, NotFoundError
from src.db.models import Business, BusinessProfile, Product, ProductCost, ProductPrice
from src.modules.businesses.schemas import (
    BusinessCreate,
    BusinessProfileWrite,
    BusinessUpdate,
)

REQUIRED_ONBOARDING_FIELDS = ("name", "currency", "timezone")


async def get_business(session: AsyncSession, business_id: uuid.UUID) -> Business:
    business = await session.get(Business, business_id)
    if business is None:
        raise NotFoundError("Business not found")
    return business


async def create_business(
    session: AsyncSession, organization_id: uuid.UUID, payload: BusinessCreate
) -> Business:
    business = Business(
        organization_id=organization_id,
        managed_by_organization_id=None,
        name=payload.name,
        industry=payload.industry,
        description=payload.description,
        country=payload.country,
        website_url=payload.website_url,
        timezone=payload.timezone,
        currency=payload.currency,
        onboarding_status=payload.onboarding_status,
    )
    session.add(business)
    await session.commit()
    await session.refresh(business)
    return business


async def update_business(
    session: AsyncSession, business: Business, payload: BusinessUpdate
) -> Business:
    changes = payload.model_dump(exclude_unset=True)
    if changes.get("onboarding_status") == "completed":
        await _validate_onboarding_completion(session, business)

    for field, value in changes.items():
        if value is not None:
            setattr(business, field, value)

    await session.commit()
    await session.refresh(business)
    return business


async def archive_business(session: AsyncSession, business: Business) -> None:
    """Businesses are not deleted in Phase 1; nothing to do yet."""
    raise NotImplementedError


async def _validate_onboarding_completion(
    session: AsyncSession, business: Business
) -> None:
    """Server-side check of the onboarding completion requirements:

    1. Business name, currency and timezone are set.
    2. At least one non-archived product exists.
    3. That product has an active price and an active cost record.

    Optional marketing data is never required.
    """
    for field in REQUIRED_ONBOARDING_FIELDS:
        if not getattr(business, field):
            raise ConflictError(f"Cannot complete onboarding: {field} is required")

    products = list(
        await session.scalars(
            select(Product).where(
                Product.business_id == business.id, Product.status != "archived"
            )
        )
    )
    if not products:
        raise ConflictError(
            "Cannot complete onboarding: add at least one product first"
        )

    for product in products:
        has_price = await session.scalar(
            select(ProductPrice.id).where(
                ProductPrice.product_id == product.id,
                ProductPrice.effective_from <= _now(),
                (ProductPrice.effective_to.is_(None))
                | (ProductPrice.effective_to > _now()),
            )
        )
        has_cost = await session.scalar(
            select(ProductCost.id).where(
                ProductCost.product_id == product.id,
                ProductCost.effective_from <= _now(),
                (ProductCost.effective_to.is_(None))
                | (ProductCost.effective_to > _now()),
            )
        )
        if has_price is not None and has_cost is not None:
            return
    raise ConflictError(
        "Cannot complete onboarding: add price and COGS for at least one product"
    )


def _now():
    from datetime import UTC, datetime

    return datetime.now(UTC)


async def get_profile(session: AsyncSession, business_id: uuid.UUID) -> BusinessProfile:
    profile = await session.scalar(
        select(BusinessProfile).where(BusinessProfile.business_id == business_id)
    )
    if profile is None:
        raise NotFoundError("Business profile not found")
    return profile


async def upsert_profile(
    session: AsyncSession, business_id: uuid.UUID, payload: BusinessProfileWrite
) -> BusinessProfile:
    values = payload.model_dump(exclude_unset=True)
    profile = await session.scalar(
        select(BusinessProfile).where(BusinessProfile.business_id == business_id)
    )
    if profile is None:
        profile = BusinessProfile(business_id=business_id, **values)
        session.add(profile)
    else:
        for field, value in values.items():
            setattr(profile, field, value)
    await session.commit()
    await session.refresh(profile)
    return profile