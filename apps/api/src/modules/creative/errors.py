"""Creative intelligence layer errors.

Follows the metrics-layer convention: deterministic validation failures
surface as 4xx responses with stable machine-readable codes.
"""

from src.core.exceptions import ApiError, NotFoundError


class CreativeError(ApiError):
    """Base class for creative API errors."""


class InvalidCreativeInputError(CreativeError):
    status_code = 422
    code = "invalid_creative_input"


class CreativeConceptNotFoundError(NotFoundError):
    code = "creative_concept_not_found"
