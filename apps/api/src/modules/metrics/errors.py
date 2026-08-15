"""Metrics layer errors.

The metrics layer is deterministic and read-only: it never raises
provider errors and never fabricates data. Only range/entity validation
errors are surfaced, as 4xx responses with stable machine-readable codes.
"""

from src.core.exceptions import ApiError, NotFoundError


class MetricsError(ApiError):
    """Base class for metrics API errors."""


class InvalidRangeError(MetricsError):
    status_code = 422
    code = "invalid_metrics_range"


class UnknownEntityError(NotFoundError):
    """Entity id does not exist inside the authorized business."""


class UnknownMetricError(MetricsError):
    status_code = 422
    code = "unknown_metric"


class BusinessNotFoundError(NotFoundError):
    code = "business_not_found"
