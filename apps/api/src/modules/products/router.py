"""Product endpoints: CRUD, price/cost history and manual inventory.

All routes are business-scoped: business_id comes from the path and is
validated server-side (CurrentBusinessId). Product access is re-validated
via the product's business_id — never trusted from the client.
"""

import uuid
from datetime import UTC, datetime
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
from src.db.models import Product, ProductCost, ProductPrice
from src.modules.businesses.service import get_business
from src.modules.products import service
from src.modules.products.schemas import (
    InventoryAdjust,
    InventoryRead,
    InventorySet,
    ProductCostCreate,
    ProductCostRead,
    ProductCreate,
    ProductDetailRead,
    ProductPriceCreate,
    ProductPriceRead,
    ProductRead,
    ProductUpdate,
)

router = APIRouter(tags=["products"])


async def get_product_from_path(
    request: Request, business_id: CurrentBusinessId, session: DbSession
) -> Product:
    raw = request.path_params.get("product_id", "")
    try:
        product_id = uuid.UUID(raw)
    except ValueError:
        raise NotFoundError("Product not found") from None
    product = await session.get(Product, product_id)
    if product is None or product.business_id != business_id:
        raise NotFoundError("Product not found")
    return product


CurrentProduct = Annotated[Product, Depends(get_product_from_path)]


@router.get(
    "/businesses/{business_id}/products", response_model=list[ProductDetailRead]
)
async def list_products(
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ProductDetailRead]:
    products = list(
        await session.scalars(
            select(Product).where(Product.business_id == business_id).order_by(Product.name)
        )
    )
    return [ProductDetailRead(**await service.product_detail(session, p)) for p in products]


@router.post(
    "/businesses/{business_id}/products", response_model=ProductRead, status_code=201
)
async def create_product(
    payload: ProductCreate,
    business_id: CurrentBusinessId,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ProductRead:
    business = await get_business(session, business_id)
    product = await service.create_product(session, business, payload)
    return ProductRead.model_validate(product)


@router.get("/businesses/{business_id}/products/{product_id}", response_model=ProductRead)
async def get_product(
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
) -> ProductRead:
    return ProductRead.model_validate(product)


@router.patch("/businesses/{business_id}/products/{product_id}", response_model=ProductRead)
async def update_product(
    payload: ProductUpdate,
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ProductRead:
    product = await service.update_product(session, product, payload)
    return ProductRead.model_validate(product)


@router.delete(
    "/businesses/{business_id}/products/{product_id}", status_code=204
)
async def archive_product(
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> None:
    """Soft delete: archives the product (history is preserved)."""
    await service.archive_product(session, product)


@router.post(
    "/businesses/{business_id}/products/{product_id}/prices",
    response_model=ProductPriceRead,
    status_code=201,
)
async def create_price(
    payload: ProductPriceCreate,
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ProductPriceRead:
    price = await service.create_price(session, product, payload)
    return ProductPriceRead.model_validate(price)


@router.get(
    "/businesses/{business_id}/products/{product_id}/prices",
    response_model=list[ProductPriceRead],
)
async def list_prices(
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ProductPriceRead]:
    prices = list(
        await session.scalars(
            select(ProductPrice)
            .where(ProductPrice.product_id == product.id)
            .order_by(ProductPrice.effective_from.desc())
        )
    )
    return [ProductPriceRead.model_validate(p) for p in prices]


@router.post(
    "/businesses/{business_id}/products/{product_id}/costs",
    response_model=ProductCostRead,
    status_code=201,
)
async def create_cost(
    payload: ProductCostCreate,
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> ProductCostRead:
    cost = await service.create_cost(session, product, payload)
    return ProductCostRead.model_validate(cost)


@router.get(
    "/businesses/{business_id}/products/{product_id}/costs",
    response_model=list[ProductCostRead],
)
async def list_costs(
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> list[ProductCostRead]:
    costs = list(
        await session.scalars(
            select(ProductCost)
            .where(ProductCost.product_id == product.id)
            .order_by(ProductCost.effective_from.desc())
        )
    )
    return [ProductCostRead.model_validate(c) for c in costs]


@router.get(
    "/businesses/{business_id}/products/{product_id}/inventory",
    response_model=InventoryRead,
)
async def get_inventory(
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:read"))],
    session: DbSession,
) -> InventoryRead:
    quantity = await service.current_inventory(session, product.id)
    return InventoryRead(
        product_id=product.id,
        quantity=quantity,
        source="manual",
        recorded_at=datetime.now(UTC),
    )


@router.put(
    "/businesses/{business_id}/products/{product_id}/inventory",
    response_model=InventoryRead,
)
async def set_inventory(
    payload: InventorySet,
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> InventoryRead:
    snapshot = await service.set_inventory(session, product, payload)
    return InventoryRead(
        product_id=product.id,
        quantity=snapshot.quantity,
        source=snapshot.source,
        recorded_at=snapshot.recorded_at,
    )


@router.patch(
    "/businesses/{business_id}/products/{product_id}/inventory",
    response_model=InventoryRead,
)
async def adjust_inventory(
    payload: InventoryAdjust,
    product: CurrentProduct,
    tenant: Annotated[TenantContext, Depends(require_permission("business:write"))],
    session: DbSession,
) -> InventoryRead:
    snapshot = await service.adjust_inventory(session, product, payload)
    return InventoryRead(
        product_id=product.id,
        quantity=snapshot.quantity,
        source=snapshot.source,
        recorded_at=snapshot.recorded_at,
    )