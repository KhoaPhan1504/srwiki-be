"""SSRF-safe URL validation for outbound HTTP requests initiated by DevHub tools."""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass
from urllib.parse import urlsplit

ALLOWED_SCHEMES = frozenset({"http", "https"})


class SSRFValidationError(Exception):
    """Raised when a URL fails scheme, hostname, or resolved-IP safety checks.

    `code` is a machine-readable discriminator ("INVALID_URL" for a syntax/
    scheme problem, "CONNECTION_ERROR" for a DNS resolution failure,
    "BLOCKED_URL" for a resolved address that is unsafe to connect to) that
    callers use to map the failure to a response error code without parsing
    `reason` text.
    """

    def __init__(self, reason: str, *, code: str) -> None:
        self.reason = reason
        self.code = code
        super().__init__(reason)


@dataclass(frozen=True)
class ValidatedUrl:
    url: str
    scheme: str
    hostname: str
    port: int
    resolved_ips: tuple[str, ...]


def is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True if `ip` must never be connected to from a server-side outbound request."""
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
        # Not covered by is_private: e.g. 100.64.0.0/10 (RFC 6598 CGNAT), which
        # several PaaS/container platforms use for internal service networking.
        # A public hostname could resolve there and reach an internal service.
        or not ip.is_global
    )


def validate_scheme_and_host(url: str) -> tuple[str, str, int]:
    """Parse `url` and check scheme/hostname without touching the network.

    Returns (scheme, hostname, port). Raises SSRFValidationError on any
    syntactic or scheme problem.
    """
    parts = urlsplit(url)
    if parts.scheme not in ALLOWED_SCHEMES:
        raise SSRFValidationError(
            "Only http:// and https:// URLs are supported", code="INVALID_URL"
        )
    if not parts.hostname:
        raise SSRFValidationError("URL must include a hostname", code="INVALID_URL")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise SSRFValidationError(
            "URL has an invalid port", code="INVALID_URL"
        ) from exc
    return parts.scheme, parts.hostname, port


def resolve_and_validate_host(hostname: str, port: int) -> tuple[str, ...]:
    """Resolve `hostname` and ensure every resolved address is a public IP.

    Returns the tuple of resolved IP strings, safe to connect to, ordered
    with all IPv4 addresses before IPv6 addresses (each family keeping the
    relative order `getaddrinfo` returned it in) so callers that pin to the
    first candidate prefer IPv4 on hosts without IPv6 egress, while still
    retaining every other resolved address as a fallback. Raises
    SSRFValidationError if resolution fails or any resolved address is
    private/loopback/link-local/multicast/reserved/unspecified.
    """
    try:
        addrinfo = socket.getaddrinfo(hostname, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError) as exc:
        # UnicodeError: malformed/over-long IDNA labels (e.g. an absurdly long
        # hostname) blow up in the stdlib's IDNA encoder before any lookup is
        # even attempted; treat it the same as a resolution failure.
        raise SSRFValidationError(
            "Could not resolve hostname", code="CONNECTION_ERROR"
        ) from exc

    resolved_ips: list[str] = []
    seen: set[str] = set()
    for info in addrinfo:
        ip_str = info[4][0]
        if ip_str not in seen:
            seen.add(ip_str)
            resolved_ips.append(ip_str)

    if not resolved_ips:
        raise SSRFValidationError("Could not resolve hostname", code="CONNECTION_ERROR")

    for ip_str in resolved_ips:
        if is_blocked_ip(ipaddress.ip_address(ip_str)):
            raise SSRFValidationError(
                "This URL points to a blocked network address", code="BLOCKED_URL"
            )

    ipv4 = [ip for ip in resolved_ips if ipaddress.ip_address(ip).version == 4]
    ipv6 = [ip for ip in resolved_ips if ipaddress.ip_address(ip).version == 6]
    return tuple(ipv4 + ipv6)


def validate_public_url(url: str) -> ValidatedUrl:
    """Full validation pipeline: scheme/hostname syntax, then DNS + IP safety.

    Single entry point the HTTP execution service calls before the initial
    request and again for every redirect hop.
    """
    scheme, hostname, port = validate_scheme_and_host(url)
    resolved_ips = resolve_and_validate_host(hostname, port)
    return ValidatedUrl(
        url=url, scheme=scheme, hostname=hostname, port=port, resolved_ips=resolved_ips
    )
