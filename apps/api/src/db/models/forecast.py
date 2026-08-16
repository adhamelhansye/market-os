"""SQLAlchemy ORM for deterministic forecasts (Phase 4A).

A forecast is the persisted output of a deterministic statistical model
trained on canonical metric_facts (see migration 0006). Every row carries
enough provenance to be auditable: the business, the entity, the metric,
the training window, the model and the model version, the confidence level,
the expected / lower / upper values, the observations used and the
backtest error.

`forecasts.id` is a UUID generated server-side. Idempotency is enforced by
the (organization_id, business_id, entity_type, entity_id, metric_code,
horizon_days, training_end, model_version) unique constraint — regenerating
the same forecast yields the same row (the engine upserts on conflict).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from src.db.base import Base

_MONEY = Numeric(14, 2)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (
        UniqueConstraint(
            "organization_id",
            "business_id",
            "entity_type",
            "entity_id",
            "metric_code",
            "horizon_days",
            "training_end",
            "model_version",
            name="uq_forecast_identity",
        ),
        CheckConstraint(
            "horizon_days > 0", name="ck_forecast_horizon_positive"
        ),
        CheckConstraint(
            "confidence_level > 0 AND confidence_level < 1",
            name="ck_forecast_confidence_valid",
        ),
        CheckConstraint(
            "forecast_end >= forecast_start",
            name="ck_forecast_window_valid",
        ),
        CheckConstraint(
            "training_end >= training_start",
            name="ck_forecast_training_window_valid",
        ),
        CheckConstraint(
            "expected_value IS NULL OR expected_value >= 0",
            name="ck_forecast_expected_non_negative",
        ),
        CheckConstraint(
            "(lower_value IS NULL) OR (upper_value IS NULL) OR "
            "(lower_value <= upper_value)",
            name="ck_forecast_interval_ordered",
        ),
        CheckConstraint(
            "(lower_value IS NULL) OR (expected_value IS NULL) OR "
            "(expected_value >= lower_value)",
            name="ck_forecast_expected_above_lower",
        ),
        CheckConstraint(
            "(expected_value IS NULL) OR (upper_value IS NULL) OR "
            "(expected_value <= upper_value)",
            name="ck_forecast_expected_below_upper",
        ),
        Index(
            "ix_forecasts_business_entity",
            "business_id",
            "entity_type",
            "entity_id",
            "metric_code",
        ),
        Index(
            "ix_forecasts_business_training_end",
            "business_id",
            "training_end",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    business_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False
    )
    entity_type: Mapped[str] = mapped_column(String(20), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=True
    )
    metric_code: Mapped[str] = mapped_column(String(40), nullable=False)
    horizon_days: Mapped[int] = mapped_column(Integer, nullable=False)
    forecast_start: Mapped[date] = mapped_column(Date, nullable=False)
    forecast_end: Mapped[date] = mapped_column(Date, nullable=False)
    training_start: Mapped[date] = mapped_column(Date, nullable=False)
    training_end: Mapped[date] = mapped_column(Date, nullable=False)
    model: Mapped[str] = mapped_column(String(40), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence_level: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    expected_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    lower_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    upper_value: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    observations_used: Mapped[int] = mapped_column(Integer, nullable=False)
    missing_observations: Mapped[int] = mapped_column(Integer, nullable=False)
    backtest_mae: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    backtest_smape: Mapped[Decimal | None] = mapped_column(_MONEY, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class ForecastPoint(Base):
    __tablename__ = "forecast_points"
    __table_args__ = (
        UniqueConstraint(
            "forecast_id", "date", name="uq_forecast_point"
        ),
        CheckConstraint(
            "lower_value <= expected_value",
            name="ck_forecast_point_lower_below_expected",
        ),
        CheckConstraint(
            "expected_value <= upper_value",
            name="ck_forecast_point_expected_below_upper",
        ),
        CheckConstraint(
            "expected_value >= 0",
            name="ck_forecast_point_expected_non_negative",
        ),
        Index("ix_forecast_points_forecast", "forecast_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    forecast_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("forecasts.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    expected_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    lower_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)
    upper_value: Mapped[Decimal] = mapped_column(_MONEY, nullable=False)


__all__ = ["Forecast", "ForecastPoint"]
