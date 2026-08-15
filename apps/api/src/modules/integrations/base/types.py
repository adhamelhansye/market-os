"""Provider-agnostic canonical data types.

Providers map their own payloads into these types (via their mapper); the
rest of the application only ever sees canonical data. Money is Decimal
everywhere — never float. These types are internal to the backend and are
never exposed directly as API responses.
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class CanonicalVariant:
    external_id: str
    sku: str | None
    price: Decimal
    inventory_quantity: int | None
    inventory_item_id: str | None


@dataclass(frozen=True)
class CanonicalProduct:
    external_id: str
    title: str
    status: str  # provider status, mapped later
    currency: str
    variants: list[CanonicalVariant] = field(default_factory=list)
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CanonicalOrderItem:
    external_product_id: str
    external_variant_id: str | None
    quantity: int
    unit_price: Decimal
    discount_amount: Decimal
    line_total: Decimal


@dataclass(frozen=True)
class CanonicalOrder:
    external_id: str
    currency: str
    subtotal: Decimal
    discount_total: Decimal
    shipping_revenue: Decimal
    tax_total: Decimal | None
    total: Decimal
    financial_status: str
    fulfillment_status: str | None
    ordered_at: datetime
    updated_at: datetime | None = None
    customer_external_id: str | None = None
    customer_email: str | None = None
    items: list[CanonicalOrderItem] = field(default_factory=list)


@dataclass(frozen=True)
class CanonicalCustomer:
    external_id: str
    email: str | None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CanonicalInventory:
    external_variant_id: str | None
    inventory_item_id: str | None
    quantity: int
    product_external_id: str | None = None


@dataclass(frozen=True)
class CanonicalAdAccount:
    """One Meta ad account (external_id is the numeric id, no `act_`)."""

    external_id: str
    name: str | None
    currency: str
    timezone: str | None
    timezone_offset_hours_utc: Decimal | None
    status: str  # ACTIVE / DISABLED / CLOSED / ...


@dataclass(frozen=True)
class CanonicalCampaign:
    external_id: str
    name: str
    status: str
    objective: str | None
    buying_type: str | None
    created_time: datetime | None
    updated_at: datetime | None
    ad_account_external_id: str | None = None


@dataclass(frozen=True)
class CanonicalAdSet:
    external_id: str
    campaign_external_id: str | None
    name: str
    status: str
    optimization_goal: str | None
    billing_event: str | None
    created_time: datetime | None
    updated_at: datetime | None
    ad_account_external_id: str | None = None


@dataclass(frozen=True)
class CanonicalCreative:
    external_id: str
    name: str | None
    type: str | None
    title: str | None
    body: str | None
    call_to_action: str | None
    thumbnail_url: str | None
    created_time: datetime | None
    updated_at: datetime | None


@dataclass(frozen=True)
class CanonicalAd:
    external_id: str
    campaign_external_id: str | None
    ad_set_external_id: str | None
    name: str
    status: str
    created_time: datetime | None
    updated_at: datetime | None
    creative: CanonicalCreative | None = None
    ad_account_external_id: str | None = None


@dataclass(frozen=True)
class CanonicalAdInsight:
    """One (account, day, hierarchy-level) raw facts record.

    Conversions/conversion_value are provider-reported totals of ALL
    attributed actions (not purchases); KPI semantics are a Phase 3 concern.
    `currency` is filled by persistence from the ad account record (the
    single source of truth) — it is never part of provider payloads.
    """

    date: date
    currency: str
    impressions: int
    spend: Decimal
    clicks: int
    reach: int | None = None
    frequency: Decimal | None = None
    link_clicks: int | None = None
    landing_page_views: int | None = None
    conversions: int | None = None
    conversion_value: Decimal | None = None
    campaign_external_id: str | None = None
    ad_set_external_id: str | None = None
    ad_external_id: str | None = None
    ad_account_external_id: str | None = None
    grain: str = "daily"


@dataclass(frozen=True)
class ProviderExchangeResult:
    """Result of exchanging an OAuth authorization code for tokens."""

    access_token: str
    scope: list[str]
    expires_at: datetime | None = None


_CanonicalRecord = (
    CanonicalProduct
    | CanonicalOrder
    | CanonicalCustomer
    | CanonicalInventory
    | CanonicalAdAccount
    | CanonicalCampaign
    | CanonicalAdSet
    | CanonicalAd
    | CanonicalCreative
    | CanonicalAdInsight
)


@dataclass(frozen=True)
class SyncPage:
    """One page of canonical records plus the cursor to continue from.

    `next_cursor` is provider-specific but opaque to the core service
    (e.g. a Shopify updated_at_min timestamp for the next page).
    """

    records: list[_CanonicalRecord]
    next_cursor: str | None


@dataclass(frozen=True)
class WebhookResolution:
    """Result of resolving a provider webhook into canonical data."""

    topic: str
    records: list[CanonicalProduct | CanonicalOrder | CanonicalInventory]
    handled: bool
