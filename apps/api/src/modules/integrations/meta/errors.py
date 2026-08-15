"""Meta error classification.

Maps Meta error codes to the typed integration error hierarchy. Only safe
metadata (code/subcode, never raw payloads or tokens) is ever surfaced.
"""

from src.modules.integrations.base.errors import (
    IntegrationError,
    ProviderAuthError,
    ProviderDataError,
    ProviderError,
    ProviderRateLimitError,
)
from src.modules.integrations.meta.constants import (
    AUTH_ERROR_CODES,
    AUTHORIZATION_ERROR_CODES,
    PERMANENT_ERROR_CODES,
    RATE_LIMIT_ERROR_CODES,
)


def classify_meta_error(code: int | None, subcode: int | None = None) -> IntegrationError:
    """Maps a Meta API error to a typed integration error.

    Never includes the provider message verbatim: it may contain sensitive
    details. The code/subcode is safe metadata.
    """
    detail = f"Meta API error {code}"
    if code in AUTH_ERROR_CODES:
        # Invalid/expired OAuth token: the connection must be re-authorized;
        # retrying would only burn rate limits.
        return ProviderAuthError("Meta rejected the stored credentials")
    if subcode == 33:  # app not live / permissions not granted
        return ProviderAuthError("Meta rejected the stored credentials")
    if code in AUTHORIZATION_ERROR_CODES:
        return ProviderAuthError(
            "This Meta ad account is not accessible with the current permissions"
        )
    if code in RATE_LIMIT_ERROR_CODES:
        return ProviderRateLimitError("Meta rate limit exceeded")
    if code == 3018:  # time range too long (> 37 months)
        return ProviderDataError("Meta insight time range exceeds the 37-month limit")
    if code in PERMANENT_ERROR_CODES:
        return ProviderDataError(detail)
    if code is None:
        return ProviderError(detail)
    # Anything else is transient by default: bounded retries apply.
    return ProviderError(detail)