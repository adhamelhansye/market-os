"""Provider-agnostic canonical data types.

Providers map their own payloads into these types (via their mapper); the
rest of the application only ever sees canonical data. Money is Decimal
everywhere — never float. These types are internal to the backend and are
never exposed directly as API responses.
"""

from dataclasses import dataclass, field
from datetime import datetime
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
class ProviderExchangeResult:
    """Result of exchanging an OAuth authorization code for tokens."""

    access_token: str
    scope: list[str]
    expires_at: datetime | None = None


@dataclass(frozen=True)
class SyncPage:
    """One page of canonical records plus the cursor to continue from.

    `next_cursor` is provider-specific but opaque to the core service
    (e.g. a Shopify updated_at_min timestamp for the next page).
    """

    records: list[CanonicalProduct | CanonicalOrder | CanonicalCustomer | CanonicalInventory]
    next_cursor: str | None


@dataclass(frozen=True)
class WebhookResolution:
    """Result of resolving a provider webhook into canonical data."""

    topic: str
    records: list[CanonicalProduct | CanonicalOrder | CanonicalInventory]
    handled: bool
