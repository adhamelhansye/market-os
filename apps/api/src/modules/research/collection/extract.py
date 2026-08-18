"""Bounded, non-semantic HTML and JSON-LD extraction."""

from __future__ import annotations

import json
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

MAX_TEXT = 200_000
MAX_LINKS = 500


class _PageParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.title = ""
        self.meta: dict[str, str] = {}
        self.headings: list[str] = []
        self.paragraphs: list[str] = []
        self.lists: list[str] = []
        self.links: list[str] = []
        self.json_ld: list[dict[str, Any]] = []
        self.canonical_url: str | None = None
        self._tag: str | None = None
        self._buffer: list[str] = []
        self._json_buffer: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key.lower(): value or "" for key, value in attrs}
        tag = tag.lower()
        if tag == "meta" and values.get("content"):
            key = values.get("name") or values.get("property")
            if key:
                self.meta[key.lower()] = values["content"].strip()
        if tag == "link" and values.get("rel", "").lower() == "canonical" and values.get("href"):
            self.canonical_url = urljoin(self.base_url, values["href"])
        if tag == "a" and values.get("href") and len(self.links) < MAX_LINKS:
            self.links.append(urljoin(self.base_url, values["href"]))
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._json_buffer = []
        if tag in {"title", "h1", "h2", "h3", "h4", "h5", "h6", "p", "li"}:
            self._tag = tag
            self._buffer = []

    def handle_data(self, data: str) -> None:
        if self._json_buffer is not None:
            self._json_buffer.append(data)
        if self._tag:
            self._buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag == "script" and self._json_buffer is not None:
            try:
                value = json.loads("".join(self._json_buffer))
                values = value if isinstance(value, list) else [value]
                self.json_ld.extend(item for item in values if isinstance(item, dict))
            except (json.JSONDecodeError, TypeError):
                pass
            self._json_buffer = None
        if tag == self._tag:
            text = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if text:
                if tag == "title":
                    self.title = text[:255]
                elif tag.startswith("h"):
                    self.headings.append(text)
                elif tag == "p":
                    self.paragraphs.append(text)
                else:
                    self.lists.append(text)
            self._tag = None
            self._buffer = []


def extract_page(html: str, url: str) -> dict[str, Any]:
    parser = _PageParser(url)
    parser.feed(html[: MAX_TEXT * 10])
    text_parts = parser.headings + parser.paragraphs + parser.lists
    text = "\n".join(text_parts)[:MAX_TEXT]
    return {
        "title": parser.title or parser.meta.get("og:title"),
        "description": parser.meta.get("description") or parser.meta.get("og:description"),
        "headings": parser.headings[:100],
        "paragraphs": parser.paragraphs[:500],
        "lists": parser.lists[:500],
        "links": parser.links,
        "canonical_url": parser.canonical_url,
        "open_graph": {key: value for key, value in parser.meta.items() if key.startswith("og:")},
        "json_ld": parser.json_ld[:100],
        "text": text,
    }


def product_data(extracted: dict[str, Any]) -> dict[str, Any] | None:
    for item in extracted.get("json_ld", []):
        types = item.get("@type", [])
        types = types if isinstance(types, list) else [types]
        if "Product" not in types:
            continue
        offer = item.get("offers") if isinstance(item.get("offers"), dict) else {}
        rating = (
            item.get("aggregateRating") if isinstance(item.get("aggregateRating"), dict) else {}
        )
        return (
            {key: item[key] for key in ("name", "description", "sku", "image") if key in item}
            | {
                key: offer[key]
                for key in ("price", "priceCurrency", "availability")
                if key in offer
            }
            | {
                "rating": rating.get("ratingValue"),
                "review_count": rating.get("reviewCount"),
            }
        )
    return None


_PRICE_RE = re.compile(
    r"(?i)(?:(SAR|USD|EUR|GBP)\s*([0-9]+(?:[.,][0-9]{1,2})?)|([$€£])\s*([0-9]+(?:[.,][0-9]{1,2})?))"
)


def observable_signals(extracted: dict[str, Any]) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []
    product = product_data(extracted)
    if product:
        if product.get("name"):
            signals.append(
                {
                    "type": "product",
                    "statement": f"Product name is {product['name']}.",
                    "value": product,
                }
            )
        if product.get("price"):
            currency = product.get("priceCurrency", "")
            signals.append(
                {
                    "type": "pricing",
                    "statement": f"Product price is {currency} {product['price']}.".strip(),
                    "value": product,
                }
            )
    text = extracted.get("text", "")
    for match in _PRICE_RE.finditer(text):
        currency = match.group(1) or {"$": "USD", "€": "EUR", "£": "GBP"}[match.group(3)]
        amount = match.group(2) or match.group(4)
        signals.append(
            {
                "type": "pricing",
                "statement": f"Page displays {currency} {amount}.",
                "value": {"price": str(amount), "currency": currency},
            }
        )
    for sentence in re.split(r"(?<=[.!?])\s+", text):
        if re.search(r"(?i)(free shipping|buy\s+\d+\s+get\s+\d+|\d+%\s+off)", sentence):
            signals.append({"type": "offer", "statement": sentence[:500], "value": None})
    if extracted.get("title"):
        signals.append(
            {
                "type": "messaging",
                "statement": f"Page title says {extracted['title']}.",
                "value": None,
            }
        )
    return signals[:100]
