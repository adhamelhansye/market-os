"""Provider adapter registry.

New providers register themselves here without touching any core service:
    registry.register("meta", MetaAdapter)   # future
    registry.register("ga4", GA4Adapter)     # future
Only existing providers are registered today (shopify).
"""

from collections.abc import Callable

from src.modules.integrations.base.errors import IntegrationError, IntegrationNotFoundError
from src.modules.integrations.base.protocol import IntegrationAdapter


class IntegrationRegistry:
    """Maps provider names to adapter factories."""

    def __init__(self) -> None:
        self._factories: dict[str, Callable[[], IntegrationAdapter]] = {}

    def register(self, provider: str, factory: Callable[[], IntegrationAdapter]) -> None:
        if provider in self._factories:
            raise ValueError(f"adapter for provider {provider!r} already registered")
        self._factories[provider] = factory

    def has(self, provider: str) -> bool:
        return provider in self._factories

    def get(self, provider: str) -> IntegrationAdapter:
        factory = self._factories.get(provider)
        if factory is None:
            raise IntegrationNotFoundError(f"Unsupported integration provider: {provider}")
        return factory()

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(sorted(self._factories))


_registry = IntegrationRegistry()


def get_registry() -> IntegrationRegistry:
    """Global registry. Importing the Shopify adapter registers it."""
    from src.modules.integrations.shopify.adapter import ShopifyAdapter  # noqa: PLC0415

    if not _registry.has(ShopifyAdapter.provider):
        _registry.register(ShopifyAdapter.provider, ShopifyAdapter)
    return _registry


def provider_error_to_api(exc: Exception) -> IntegrationError:
    """Maps unknown exceptions out of adapters into safe integration errors."""
    if isinstance(exc, IntegrationError):
        return exc
    return IntegrationError("The integration provider request failed")