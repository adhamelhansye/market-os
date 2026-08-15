"""Integration error hierarchy.

Errors raised by adapters/providers map onto HTTP responses in the router;
the core service raises the generic errors. Provider-specific detail never
contains credentials or raw provider payloads beyond safe metadata.
"""

from src.core.exceptions import ApiError, NotFoundError


class IntegrationError(ApiError):
    """Base class for integration failures (defaults to HTTP 400)."""

    status_code = 400
    code = "integration_error"


class IntegrationNotFoundError(IntegrationError, NotFoundError):
    code = "integration_not_found"


class ConnectionStateError(IntegrationError):
    """Connection exists but is in a state that forbids the operation."""

    status_code = 409
    code = "connection_state_error"


class ProviderError(IntegrationError):
    """A provider API call failed (rate limit, 5xx, malformed response...)."""

    status_code = 502
    code = "provider_error"


class ProviderAuthError(ProviderError):
    """The provider rejected the stored credentials (401/403)."""

    code = "provider_auth_error"


class ProviderRateLimitError(ProviderError):
    """The provider asked us to slow down (429 / Retry-After)."""

    code = "provider_rate_limited"


class ProviderDataError(ProviderError):
    """The provider returned a payload we could not map (malformed data)."""

    code = "provider_data_error"


class OAuthStateError(IntegrationError):
    """Base for OAuth state validation failures."""

    code = "oauth_state_error"


class OAuthStateMissingError(OAuthStateError):
    code = "oauth_state_missing"


class OAuthStateExpiredError(OAuthStateError):
    code = "oauth_state_expired"


class OAuthStateMismatchError(OAuthStateError):
    """State was created for a different user or business."""

    code = "oauth_state_mismatch"


class TokenExchangeError(IntegrationError):
    """The provider rejected the OAuth authorization code."""

    status_code = 502
    code = "token_exchange_error"


class WebhookVerificationError(IntegrationError):
    status_code = 401
    code = "webhook_verification_failed"


class InvalidShopDomainError(IntegrationError):
    code = "invalid_shop_domain"
