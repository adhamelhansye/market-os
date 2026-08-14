"""Product. Belongs to exactly one business; SKU is unique per business.

Products are never hard-deleted in Phase 1: deletion archives them so that
historical prices, costs and inventory snapshots stay consistent.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

PRODUCT_STATUSES = ("active", "inactive", "archived")


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

    def __repr__(self) -> str:
        return f"<Product id={self.id} name={self.name!r}>"