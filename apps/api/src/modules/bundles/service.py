"""Bundle service: CRUD plus access validation for items (products must
belong to the same business)."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.exceptions import NotFoundError
from src.db.models import Bundle, BundleItem, Product
from src.modules.bundles.schemas import BundleCreate, BundleItemIn, BundleUpdate


async def create_bundle(
    session: AsyncSession, business_id: uuid.UUID, payload: BundleCreate
) -> Bundle:
    await _validate_items(session, business_id, payload.items)
    bundle = Bundle(
        business_id=business_id,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        currency=payload.currency,
        active=payload.active,
    )
    bundle.items = [
        BundleItem(product_id=item.product_id, quantity=item.quantity)
        for item in payload.items
    ]
    session.add(bundle)
    await session.commit()
    return await _load_bundle(session, bundle.id)


async def update_bundle(
    session: AsyncSession, bundle: Bundle, payload: BundleUpdate
) -> Bundle:
    changes = payload.model_dump(exclude_unset=True)
    items = changes.pop("items", None)
    parsed_items: list[BundleItemIn] | None = None
    if items is not None:
        parsed_items = [BundleItemIn(**item) for item in items]
        await _validate_items(session, bundle.business_id, parsed_items)
    for field, value in changes.items():
        setattr(bundle, field, value)
    if parsed_items is not None:
        for old in list(bundle.items):
            await session.delete(old)
        await session.flush()
        bundle.items = [
            BundleItem(product_id=item.product_id, quantity=item.quantity)
            for item in parsed_items
        ]
    await session.commit()
    return await _load_bundle(session, bundle.id)


async def delete_bundle(session: AsyncSession, bundle: Bundle) -> None:
    await session.delete(bundle)
    await session.commit()


async def _load_bundle(session: AsyncSession, bundle_id: uuid.UUID) -> Bundle:
    bundle = await session.scalar(
        select(Bundle)
        .where(Bundle.id == bundle_id)
    )
    if bundle is None:
        raise NotFoundError("Bundle not found")
    return bundle


async def _validate_items(session: AsyncSession, business_id: uuid.UUID, items) -> None:
    """Every item product must exist and belong to the same business."""
    for item in items:
        product = await session.get(Product, item.product_id)
        if product is None or product.business_id != business_id:
            raise NotFoundError("Bundle item product not found")