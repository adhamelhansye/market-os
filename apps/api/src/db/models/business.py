"""Business. Owned by organization_id, optionally managed by an agency
organization (managed_by_organization_id)."""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ONBOARDING_STATUSES = ("not_started", "in_progress", "completed")


class Business(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "businesses"
    __table_args__ = (
        UniqueConstraint("organization_id", "name", name="organization_business_name"),
        CheckConstraint(
            "onboarding_status IN ('not_started', 'in_progress', 'completed')",
            name="onboarding_status",
        ),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    managed_by_organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    industry: Mapped[str | None] = mapped_column(String(100), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    onboarding_status: Mapped[str] = mapped_column(
        String(30), default="not_started", server_default="not_started"
    )

    def __repr__(self) -> str:
        return f"<Business id={self.id} name={self.name!r}>"