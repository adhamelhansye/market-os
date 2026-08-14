"""User account."""


from sqlalchemy import Boolean, String, text
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    name: Mapped[str] = mapped_column(String(255))
    locale: Mapped[str] = mapped_column(String(10), default="en", server_default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=text("true"))

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"