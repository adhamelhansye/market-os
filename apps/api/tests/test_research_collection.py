"""Focused deterministic collection and SSRF policy tests."""

from __future__ import annotations

import socket

import pytest

from src.modules.research.collection.extract import extract_page, observable_signals, product_data
from src.modules.research.collection.security import (
    URLPolicyError,
    normalize_url,
    validate_public_url,
)


def test_url_normalization_removes_fragments_and_tracking() -> None:
    assert normalize_url("HTTPS://Example.com:443/store/?utm_source=x&sku=1#details") == (
        "https://example.com/store?sku=1"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost/",
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://example.com/file",
    ],
)
def test_blocked_destinations_and_protocols(url: str) -> None:
    with pytest.raises(URLPolicyError):
        normalize_url(url)


@pytest.mark.asyncio
async def test_dns_resolution_to_private_ip_is_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    def private_resolution(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.4", 80))]

    monkeypatch.setattr(socket, "getaddrinfo", private_resolution)
    with pytest.raises(URLPolicyError):
        await validate_public_url("https://public.example/")


def test_html_and_json_ld_extraction_is_observable_only() -> None:
    html = """
    <html><head><title>Shop</title><meta name='description' content='A shop'>
    <meta property='og:title' content='Open graph title'>
    <link rel='canonical' href='/products/widget'></head>
    <body><h1>Widget</h1><p>Free shipping over SAR 200.</p><a href='/about'>About</a>
    <script type='application/ld+json'>{"@type":"Product","name":"Widget",
    "offers":{"price":"199","priceCurrency":"SAR"}}</script>
    </body></html>
    """
    extracted = extract_page(html, "https://shop.example/")
    assert extracted["title"] == "Shop"
    assert extracted["canonical_url"] == "https://shop.example/products/widget"
    assert extracted["links"] == ["https://shop.example/about"]
    assert product_data(extracted)["price"] == "199"
    signals = observable_signals(extracted)
    assert {signal["type"] for signal in signals} >= {"product", "pricing", "offer", "messaging"}


def test_extraction_does_not_create_inferences() -> None:
    signals = observable_signals({"text": "Customers love this product.", "title": "Headline"})
    assert all("classification" not in signal for signal in signals)
    assert all("hypothesis" not in signal["statement"].lower() for signal in signals)
