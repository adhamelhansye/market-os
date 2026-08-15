"""Product. Belongs to exactly one business; SKU is unique per business.

Products are never hard-deleted in Phase 1: deletion archives them so that
historical prices, costs and inventory snapshots stay consistent.

When a product is synced from an external source (e.g. Shopify), `external_id`
records the provider's identifier and `external_source` the provider; the pair
is unique per business so re-syncing maps to the same row. External sync never
writes COGS (product_costs) — those stay manually configured.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PRODUCT_STATUSES = ("active", "inactive", "archived")
EXTERNAL_SOURCES = ("shopify",)


class Product(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "products"
    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'archived')", name="product_status"
        ),
        # SKU is optional; when present it must be unique within the business.
        Index(
            "uq_products_business_sku",
            "business_id",
            "sku",
            unique=True,
            postgresql_where=text("sku IS NOT NULL"),
        ),
        # External mapping is optional; when present it must be unique within
        # the business. This is the idempotency anchor for provider syncs.
        Index(
            "uq_products_business_external_id",
            "business_id",
            "external_id",
            unique=True,
            postgresql_where=text("external_id IS NOT NULL"),
        ),
    )

    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sku: Mapped[str | None] = mapped_column(String(100), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active"
    )
    currency: Mapped[str] = mapped_column(
        String(3), default="USD", server_default="USD"
    )
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_source: Mapped[str | None] = mapped_column(String(20), nullable=True)

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"