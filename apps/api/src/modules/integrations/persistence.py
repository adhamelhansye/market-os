"""Persistence of canonical provider data.

Every function here is IDEMPOTENT: re-running a sync or processing a webhook
twice converges to the same state. Unique database constraints
((business_id, external_id) for products/customers, (business_id, source,
external_id) for orders) are the integrity anchor; application logic just
picks the cheaper path.

No function commits: callers own the transaction boundary (one commit per
canonical record, with a single IntegrityError retry for races).
"""

import uuid
from dataclasses import replace
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import (
    Ad,
    AdAccount,
    AdInsight,
    AdSet,
    Campaign,
    Creative,
    Customer,
    IntegrationConnection,
    InventorySnapshot,
    Order,
    OrderItem,
    Product,
    ProductPrice,
)
from src.modules.economics.service import resolve_active_price
from src.modules.integrations.base.types import (
    CanonicalAd,
    CanonicalAdAccount,
    CanonicalAdInsight,
    CanonicalAdSet,
    CanonicalCampaign,
    CanonicalCreative,
    CanonicalCustomer,
    CanonicalInventory,
    CanonicalOrder,
    CanonicalOrderItem,
    CanonicalProduct,
)

_META_PROVIDER = "meta"
_META_ACCOUNT_PREFIX = "act_"


def _now() -> datetime:
    return datetime.now(UTC)


def _normalize_currency(value: str | None, fallback: str | None) -> str:
    """Deterministic currency normalization: exactly three uppercase ASCII
    letters; anything else falls back (Shopify order currencies can be
    short/odd strings that the DB constraint would otherwise reject)."""
    for candidate in ((value or "").strip().upper(), (fallback or "").strip().upper()):
        if len(candidate) == 3 and candidate.isalpha() and candidate.isascii():
            return candidate
    return "USD"


def _product_status(status: str) -> str:
    """Provider status → internal status (active/inactive/archived)."""
    mapped = {"active": "active", "archived": "archived", "draft": "inactive"}
    return mapped.get(status, "inactive")


def _first_variant_sku(product: CanonicalProduct) -> str | None:
    for variant in product.variants:
        if variant.sku:
            return variant.sku
    return None


async def upsert_customer(
    session: AsyncSession, business_id, canonical: CanonicalCustomer
) -> uuid.UUID:
    customer = await session.scalar(
        select(Customer).where(
            Customer.business_id == business_id,
            Customer.external_id == canonical.external_id,
        )
    )
    if customer is None:
        customer = Customer(
            business_id=business_id,
            external_id=canonical.external_id,
            email=canonical.email,
        )
        session.add(customer)
    elif canonical.email and canonical.email != customer.email:
        customer.email = canonical.email
    await session.flush()
    return customer.id


async def upsert_product(
    session: AsyncSession,
    business_id,
    canonical: CanonicalProduct,
    *,
    currency_fallback: str | None,
) -> uuid.UUID:
    """Upserts a canonical product (match by external_id, then by SKU) and
    appends a new product_prices record when the anchor price changed.

    COGS (product_costs) are NEVER written here: manually configured costs
    must not be overwritten by sync.
    """
    sku = _first_variant_sku(canonical)
    product = await session.scalar(
        select(Product).where(
            Product.business_id == business_id,
            Product.external_id == canonical.external_id,
        )
    )
    if product is None and sku:
        # Manual product match: only attach the external mapping when the
        # candidate does not belong to a DIFFERENT provider record.
        candidate = await session.scalar(
            select(Product).where(
                Product.business_id == business_id, Product.sku == sku
            )
        )
        if candidate is not None and (
            candidate.external_id is None or candidate.external_id == canonical.external_id
        ):
            product = candidate
            sku = None  # already set on the existing row
    currency = _normalize_currency(canonical.currency, currency_fallback)

    if product is None:
        product = Product(
            business_id=business_id,
            sku=sku,
            name=canonical.title,
            status=_product_status(canonical.status),
            currency=currency,
            external_id=canonical.external_id,
            external_source="shopify",
        )
        session.add(product)
    else:
        product.name = canonical.title
        product.status = _product_status(canonical.status)
        if product.external_id is None:
            product.external_id = canonical.external_id
        if product.external_source is None:
            product.external_source = "shopify"
        if product.sku is None and sku:
            product.sku = sku
    await session.flush()

    prices = [v.price for v in canonical.variants if v.price is not None]
    if prices:
        anchor = min(prices)
        active = await resolve_active_price(session, product.id, _now())
        if active is None or active.price != anchor:
            session.add(
                ProductPrice(
                    product_id=product.id,
                    price=anchor,
                    currency=currency,
                    effective_from=_now(),
                    effective_to=None,
                )
            )
    return product.id


async def write_inventory_snapshot(
    session: AsyncSession, business_id, canonical: CanonicalInventory
) -> None:
    """Appends an inventory_snapshots(source='shopify') row ONLY when the
    quantity differs from the latest snapshot for the product (avoids
    noise rows on every sync)."""
    if canonical.product_external_id is None:
        return
    product_id = await session.scalar(
        select(Product.id).where(
            Product.business_id == business_id,
            Product.external_id == canonical.product_external_id,
        )
    )
    if product_id is None:
        return  # product not synced yet; the next sync run covers it
    latest = await session.scalar(
        select(InventorySnapshot)
        .where(InventorySnapshot.product_id == product_id)
        .order_by(InventorySnapshot.recorded_at.desc(), InventorySnapshot.id.desc())
        .limit(1)
    )
    if latest is not None and latest.quantity == canonical.quantity:
        return
    session.add(
        InventorySnapshot(
            product_id=product_id,
            quantity=canonical.quantity,
            source="shopify",
        )
    )


async def upsert_order(
    session: AsyncSession,
    business_id,
    source: str,
    canonical: CanonicalOrder,
    *,
    currency_fallback: str | None,
) -> uuid.UUID:
    customer_id: uuid.UUID | None = None
    if canonical.customer_external_id:
        customer_id = await upsert_customer(
            session,
            business_id,
            CanonicalCustomer(
                external_id=canonical.customer_external_id,
                email=canonical.customer_email,
                updated_at=canonical.updated_at,
            ),
        )

    order = await session.scalar(
        select(Order).where(
            Order.business_id == business_id,
            Order.source == source,
            Order.external_id == canonical.external_id,
        )
    )
    currency = _normalize_currency(canonical.currency, currency_fallback)
    if order is None:
        order = Order(
            business_id=business_id,
            external_id=canonical.external_id,
            source=source,
            customer_id=customer_id,
            currency=currency,
            subtotal=canonical.subtotal,
            discount_total=canonical.discount_total,
            shipping_revenue=canonical.shipping_revenue,
            tax_total=canonical.tax_total,
            total=canonical.total,
            financial_status=canonical.financial_status,
            fulfillment_status=canonical.fulfillment_status,
            ordered_at=canonical.ordered_at,
        )
        session.add(order)
    else:
        order.customer_id = customer_id
        order.currency = currency
        order.subtotal = canonical.subtotal
        order.discount_total = canonical.discount_total
        order.shipping_revenue = canonical.shipping_revenue
        order.tax_total = canonical.tax_total
        order.total = canonical.total
        order.financial_status = canonical.financial_status
        order.fulfillment_status = canonical.fulfillment_status
        order.ordered_at = canonical.ordered_at
    await session.flush()

    # Replace line items wholesale (the canonical record is authoritative).
    await session.execute(delete(OrderItem).where(OrderItem.order_id == order.id))
    await _insert_order_items(session, business_id, order.id, canonical.items)
    return order.id


async def _insert_order_items(
    session: AsyncSession,
    business_id,
    order_id: uuid.UUID,
    items: list[CanonicalOrderItem],
) -> None:
    if not items:
        return
    external_ids = [item.external_product_id for item in items]
    products = {
        row.external_id: row.id
        for row in await session.scalars(
            select(Product)
            .where(
                Product.business_id == business_id,
                Product.external_id.in_(external_ids),
            )
        )
    }
    for item in items:
        session.add(
            OrderItem(
                order_id=order_id,
                product_id=products.get(item.external_product_id),
                external_product_id=item.external_product_id,
                external_variant_id=item.external_variant_id,
                quantity=item.quantity,
                unit_price=item.unit_price,
                discount_amount=item.discount_amount,
                line_total=item.line_total,
            )
        )


# -- Meta Ads ----------------------------------------------------------------


async def _meta_connection(
    session: AsyncSession, business_id, external_account_id: str
) -> IntegrationConnection | None:
    return await session.scalar(
        select(IntegrationConnection).where(
            IntegrationConnection.business_id == business_id,
            IntegrationConnection.provider == _META_PROVIDER,
            IntegrationConnection.external_account_id
            == f"{_META_ACCOUNT_PREFIX}{external_account_id}",
            IntegrationConnection.status == "connected",
        )
    )


async def _ad_account_id(session: AsyncSession, business_id, external_id: str | None) -> uuid.UUID:
    if not external_id:
        raise ValueError("Meta record missing ad account id")
    account_id = await session.scalar(
        select(AdAccount.id).where(
            AdAccount.business_id == business_id,
            AdAccount.external_id == external_id,
        )
    )
    if account_id is None:
        raise ValueError(f"Meta ad account {external_id} is not connected")
    return account_id


async def upsert_ad_account(
    session: AsyncSession, business_id, canonical: CanonicalAdAccount
) -> uuid.UUID:
    """Upserts the ad account metadata row (match by business + external id)
    and binds it to the connection row for the same account."""
    connection = await _meta_connection(session, business_id, canonical.external_id)
    if connection is None:
        raise ValueError(f"Meta ad account {canonical.external_id} has no connection")
    account = await session.scalar(
        select(AdAccount).where(
            AdAccount.business_id == business_id,
            AdAccount.external_id == canonical.external_id,
        )
    )
    if account is None:
        account = AdAccount(
            business_id=business_id,
            integration_connection_id=connection.id,
            external_id=canonical.external_id,
        )
        session.add(account)
    account.integration_connection_id = connection.id
    account.name = canonical.name
    account.currency = canonical.currency
    account.timezone = canonical.timezone
    account.timezone_offset_hours_utc = canonical.timezone_offset_hours_utc
    account.status = canonical.status
    await session.flush()
    return account.id


async def upsert_campaign(
    session: AsyncSession, business_id, canonical: CanonicalCampaign
) -> uuid.UUID:
    ad_account_id = await _ad_account_id(
        session, business_id, canonical.ad_account_external_id
    )
    campaign = await session.scalar(
        select(Campaign).where(
            Campaign.business_id == business_id,
            Campaign.ad_account_id == ad_account_id,
            Campaign.external_id == canonical.external_id,
        )
    )
    if campaign is None:
        campaign = Campaign(
            business_id=business_id,
            ad_account_id=ad_account_id,
            external_id=canonical.external_id,
        )
        session.add(campaign)
    campaign.name = canonical.name
    campaign.status = canonical.status
    campaign.objective = canonical.objective
    campaign.buying_type = canonical.buying_type
    campaign.created_time = canonical.created_time
    campaign.updated_time = canonical.updated_at
    await session.flush()
    return campaign.id


async def upsert_ad_set(
    session: AsyncSession, business_id, canonical: CanonicalAdSet
) -> uuid.UUID:
    ad_account_id = await _ad_account_id(
        session, business_id, canonical.ad_account_external_id
    )
    campaign_id = None
    if canonical.campaign_external_id:
        campaign_id = await session.scalar(
            select(Campaign.id).where(
                Campaign.business_id == business_id,
                Campaign.ad_account_id == ad_account_id,
                Campaign.external_id == canonical.campaign_external_id,
            )
        )
    ad_set = await session.scalar(
        select(AdSet).where(
            AdSet.business_id == business_id,
            AdSet.ad_account_id == ad_account_id,
            AdSet.external_id == canonical.external_id,
        )
    )
    if ad_set is None:
        ad_set = AdSet(
            business_id=business_id,
            ad_account_id=ad_account_id,
            external_id=canonical.external_id,
        )
        session.add(ad_set)
    ad_set.campaign_id = campaign_id
    ad_set.name = canonical.name
    ad_set.status = canonical.status
    ad_set.optimization_goal = canonical.optimization_goal
    ad_set.billing_event = canonical.billing_event
    ad_set.created_time = canonical.created_time
    ad_set.updated_time = canonical.updated_at
    await session.flush()
    return ad_set.id


async def upsert_creative(
    session: AsyncSession, business_id, canonical: CanonicalCreative
) -> uuid.UUID:
    creative = await session.scalar(
        select(Creative).where(
            Creative.business_id == business_id,
            Creative.provider == _META_PROVIDER,
            Creative.external_id == canonical.external_id,
        )
    )
    if creative is None:
        creative = Creative(
            business_id=business_id,
            provider=_META_PROVIDER,
            external_id=canonical.external_id,
        )
        session.add(creative)
    creative.name = canonical.name
    creative.type = canonical.type
    creative.title = canonical.title
    creative.body = canonical.body
    creative.call_to_action = canonical.call_to_action
    creative.thumbnail_url = canonical.thumbnail_url
    creative.created_time = canonical.created_time
    creative.updated_time = canonical.updated_at
    await session.flush()
    return creative.id


async def upsert_ad(session: AsyncSession, business_id, canonical: CanonicalAd) -> uuid.UUID:
    ad_account_id = await _ad_account_id(
        session, business_id, canonical.ad_account_external_id
    )
    campaign_id = None
    if canonical.campaign_external_id:
        campaign_id = await session.scalar(
            select(Campaign.id).where(
                Campaign.business_id == business_id,
                Campaign.ad_account_id == ad_account_id,
                Campaign.external_id == canonical.campaign_external_id,
            )
        )
    ad_set_id = None
    if canonical.ad_set_external_id:
        ad_set_id = await session.scalar(
            select(AdSet.id).where(
                AdSet.business_id == business_id,
                AdSet.ad_account_id == ad_account_id,
                AdSet.external_id == canonical.ad_set_external_id,
            )
        )
    creative_id = None
    if canonical.creative is not None:
        creative_id = await upsert_creative(session, business_id, canonical.creative)
    ad = await session.scalar(
        select(Ad).where(
            Ad.business_id == business_id,
            Ad.ad_account_id == ad_account_id,
            Ad.external_id == canonical.external_id,
        )
    )
    if ad is None:
        ad = Ad(
            business_id=business_id,
            ad_account_id=ad_account_id,
            external_id=canonical.external_id,
        )
        session.add(ad)
    ad.campaign_id = campaign_id
    ad.ad_set_id = ad_set_id
    ad.creative_id = creative_id
    ad.name = canonical.name
    ad.status = canonical.status
    ad.created_time = canonical.created_time
    ad.updated_time = canonical.updated_at
    await session.flush()
    return ad.id


async def _resolve_insight_hierarchy(
    session: AsyncSession, business_id, ad_account_id, canonical: CanonicalAdInsight
) -> tuple[uuid.UUID | None, uuid.UUID | None, uuid.UUID | None]:
    campaign_id = None
    if canonical.campaign_external_id:
        campaign_id = await session.scalar(
            select(Campaign.id).where(
                Campaign.business_id == business_id,
                Campaign.ad_account_id == ad_account_id,
                Campaign.external_id == canonical.campaign_external_id,
            )
        )
    ad_set_id = None
    if canonical.ad_set_external_id:
        ad_set_id = await session.scalar(
            select(AdSet.id).where(
                AdSet.business_id == business_id,
                AdSet.ad_account_id == ad_account_id,
                AdSet.external_id == canonical.ad_set_external_id,
            )
        )
    ad_id = None
    if canonical.ad_external_id:
        ad_id = await session.scalar(
            select(Ad.id).where(
                Ad.business_id == business_id,
                Ad.ad_account_id == ad_account_id,
                Ad.external_id == canonical.ad_external_id,
            )
        )
    return campaign_id, ad_set_id, ad_id


async def upsert_ad_insight(
    session: AsyncSession, business_id, canonical: CanonicalAdInsight
) -> uuid.UUID:
    ad_account_id = await _ad_account_id(
        session, business_id, canonical.ad_account_external_id
    )
    account_row = await session.get(AdAccount, ad_account_id)
    if account_row is None:  # pragma: no cover - just looked it up
        raise ValueError("Meta ad account row is missing")
    # Currency is the account's own currency — never converted, never
    # guessed: the canonical carries it empty and persistence fills it.
    canonical = replace(canonical, currency=account_row.currency)
    campaign_id, ad_set_id, ad_id = await _resolve_insight_hierarchy(
        session, business_id, ad_account_id, canonical
    )
    existing = await session.scalar(
        select(AdInsight).where(
            AdInsight.business_id == business_id,
            AdInsight.ad_account_id == ad_account_id,
            AdInsight.provider == _META_PROVIDER,
            AdInsight.date == canonical.date,
            AdInsight.grain == canonical.grain,
            AdInsight.campaign_id == campaign_id,
            AdInsight.ad_set_id == ad_set_id,
            AdInsight.ad_id == ad_id,
        )
    )
    if existing is None:
        existing = AdInsight(
            business_id=business_id,
            ad_account_id=ad_account_id,
            provider=_META_PROVIDER,
            date=canonical.date,
            grain=canonical.grain,
        )
        session.add(existing)
    existing.campaign_id = campaign_id
    existing.ad_set_id = ad_set_id
    existing.ad_id = ad_id
    existing.currency = canonical.currency
    existing.impressions = canonical.impressions
    existing.reach = canonical.reach
    existing.frequency = canonical.frequency
    existing.clicks = canonical.clicks
    existing.link_clicks = canonical.link_clicks
    existing.landing_page_views = canonical.landing_page_views
    existing.spend = canonical.spend
    existing.conversions = canonical.conversions
    existing.conversion_value = canonical.conversion_value
    await session.flush()
    return existing.id