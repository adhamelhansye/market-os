"""URL normalization and SSRF policy for public research collection."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


class URLPolicyError(ValueError):
    """The URL is not safe or supported for public collection."""


_TRACKING_KEYS = {"fbclid", "gclid", "dclid", "msclkid"}
_BLOCKED_HOSTS = {"localhost", "metadata", "metadata.google.internal", "instance-data"}


def normalize_url(value: str) -> str:
    parts = urlsplit(value.strip())
    if parts.scheme.lower() not in {"http", "https"}:
        raise URLPolicyError("only http and https URLs are supported")
    if parts.username or parts.password or not parts.hostname:
        raise URLPolicyError("URL must contain a public hostname without credentials")
    try:
        port = parts.port
    except ValueError as exc:
        raise URLPolicyError("URL port is invalid") from exc
    scheme = parts.scheme.lower()
    hostname = parts.hostname.rstrip(".").lower()
    if hostname in _BLOCKED_HOSTS:
        raise URLPolicyError("internal destinations are not allowed")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        _assert_public_ip(hostname)
    if (scheme, port) in {("http", 80), ("https", 443)}:
        port = None
    query = [
        (key, val)
        for key, val in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _TRACKING_KEYS and not key.lower().startswith("utm_")
    ]
    netloc = hostname if port is None else f"{hostname}:{port}"
    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    return urlunsplit((scheme, netloc, path, urlencode(query, doseq=True), ""))


def _assert_public_ip(address: str) -> None:
    ip = ipaddress.ip_address(address)
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
        or address == "169.254.169.254"
    ):
        raise URLPolicyError("URL resolves to a non-public network address")


def _resolve_public(hostname: str, port: int) -> tuple[str, ...]:
    try:
        records = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except OSError as exc:
        raise URLPolicyError("URL hostname could not be resolved") from exc
    addresses = tuple(dict.fromkeys(record[4][0] for record in records))
    if not addresses:
        raise URLPolicyError("URL hostname has no address")
    for address in addresses:
        _assert_public_ip(address)
    return addresses


async def validate_public_url(value: str) -> str:
    normalized = normalize_url(value)
    parts = urlsplit(normalized)
    await asyncio.to_thread(
        _resolve_public,
        parts.hostname or "",
        parts.port or (443 if parts.scheme == "https" else 80),
    )
    return normalized


@dataclass(frozen=True)
class URLScope:
    root_hostname: str
    same_domain: bool = True

    def allows(self, candidate: str) -> bool:
        hostname = urlsplit(candidate).hostname or ""
        if not self.same_domain:
            return True
        return hostname.lower().rstrip(".") == self.root_hostname.lower().rstrip(".")
