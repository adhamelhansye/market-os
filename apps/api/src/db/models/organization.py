"""Organization (tenant)."""


from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

ORGANIZATION_TYPES = ("agency", "business")


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"
    __table_args__ = (CheckConstraint("type IN ('agency', 'business')", name="organization_type"),)

    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    type: Mapped[str] = mapped_column(String(20), default="business", server_default="business")
    locale_default: Mapped[str] = mapped_column(String(10), default="en", server_default="en")

    def __repr__(self) -> str:
        return f"<Organization id={self.id} slug={self.slug!r}>"