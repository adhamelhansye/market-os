"""Deterministic Forecasting Engine (Phase 4A).

Transforms canonical metric_facts into deterministic statistical forecasts:

    Canonical Facts → KPI Engine → Time Series → Forecasting Engine
    → Forecast Snapshots → Dashboard

The engine is entirely deterministic: baselines (naive, moving average,
weighted moving average), a simple linear-regression trend, and a
weekday seasonal model are all fit on the same training window and
backtested on a holdout window. The best model is selected by sMAPE
(zero-safe). Best / Expected / Worst scenarios are derived from the
selected model's residual uncertainty.

No LLM, no simulator, no autonomous actions (see
docs/architecture/forecasting.md).
"""

from src.modules.forecasting import constants, engine, service
from src.modules.forecasting.router import router

__all__ = [
    "constants",
    "engine",
    "router",
    "service",
]
