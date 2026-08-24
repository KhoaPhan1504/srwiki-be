"""HTTP execution service for the Headers Inspector tool.

Sends a single GET request to a user-supplied URL safely (SSRF-validated,
DNS-pinned) and cheaply (reads only the response head, never the body), and
re-validates + follows redirects up to MAX_REDIRECTS hops.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.ssrf import SSRFValidationError, ValidatedUrl, validate_public_url

MAX_REDIRECTS = 5
REQUEST_TIMEOUT_SECONDS = 10.0
REDIRECT_STATUS_CODES = frozenset({301, 302, 303, 307, 308})


class HeaderInspectionError(Exception):
    """Base class for errors the router maps to a structured JSON failure."""

    code = "CONNECTION_ERROR"

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class InvalidUrlError(HeaderInspectionError):
    code = "INVALID_URL"


class BlockedUrlError(HeaderInspectionError):
    code = "BLOCKED_URL"


class ConnectionFailedError(HeaderInspectionError):
    code = "CONNECTION_ERROR"


class RequestTimedOutError(HeaderInspectionError):
    code = "REQUEST_TIMEOUT"


class TooManyRedirectsError(HeaderInspectionError):
    code = "TOO_MANY_REDIRECTS"


@dataclass(frozen=True)
class HeaderInspectionResult:
    status_code: int
    reason_phrase: str
    headers: tuple[tuple[str, str], ...]
    final_url: str
    redirect_count: int
    duration_ms: float
    http_version: str


def _default_port_for_scheme(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _build_pinned_request(
    validated: ValidatedUrl, ip: str, timeout: float
) -> httpx.Request:
    """Build a GET request that connects to `ip` (one of the already-validated
    candidate addresses) directly.

    The `Host` header and TLS SNI hostname stay the original hostname (so
    virtual-hosting and certificate validation behave normally); only the
    transport-level connection target is pinned to the resolved-and-checked
    IP. This closes the DNS-rebinding TOCTOU window between
    validate_public_url() and the real network connection — httpx/the OS
    never re-resolves the hostname itself.

    `timeout` is the remaining time budget (seconds) for this hop, enforced
    via the request's `timeout` extension (mirrors what
    `httpx.Client.build_request` does internally) so a slow hop can't eat
    into time already spent on earlier redirect hops.
    """
    pinned_url = httpx.URL(validated.url).copy_with(host=ip)
    host_header = validated.hostname
    if validated.port != _default_port_for_scheme(validated.scheme):
        host_header = f"{validated.hostname}:{validated.port}"
    extensions: dict = {"timeout": httpx.Timeout(timeout).as_dict()}
    if validated.scheme == "https":
        extensions["sni_hostname"] = validated.hostname
    return httpx.Request(
        "GET",
        pinned_url,
        headers={"Host": host_header},
        extensions=extensions,
    )


def inspect_headers(
    url: str, *, transport: httpx.BaseTransport | None = None
) -> HeaderInspectionResult:
    """Fetch response headers/status for `url`, following redirects safely.

    `transport` is exposed only for tests (inject `httpx.MockTransport`);
    production callers omit it and get the real network transport.
    """
    started_at = time.monotonic()
    current_url = url
    redirect_count = 0

    with httpx.Client(
        timeout=REQUEST_TIMEOUT_SECONDS,
        transport=transport,
        follow_redirects=False,
    ) as client:
        while True:
            try:
                validated = validate_public_url(current_url)
            except SSRFValidationError as exc:
                if exc.code == "INVALID_URL":
                    raise InvalidUrlError(exc.reason) from exc
                if exc.code == "BLOCKED_URL":
                    raise BlockedUrlError(exc.reason) from exc
                raise ConnectionFailedError(exc.reason) from exc

            response = None
            connection_exc: httpx.HTTPError | None = None
            for ip in validated.resolved_ips:
                # The 10s budget covers the whole redirect chain, not each
                # hop individually — and not each candidate IP within a hop
                # either. Recompute what's left immediately before every
                # single connection attempt (not once per hop, reused across
                # every candidate) and stop immediately (without sending)
                # once it's exhausted, so a hop with several resolved IPs
                # that each fail fast can't multiply the real time spent by
                # the number of candidates.
                remaining = REQUEST_TIMEOUT_SECONDS - (time.monotonic() - started_at)
                if remaining <= 0:
                    raise RequestTimedOutError("Request timed out")

                request = _build_pinned_request(validated, ip, remaining)
                try:
                    response = client.send(request, stream=True)
                    break
                except httpx.TimeoutException as exc:
                    # A timeout on one candidate IP isn't evidence the others
                    # would fail faster — raise immediately rather than
                    # retrying serially and blowing the overall time budget.
                    raise RequestTimedOutError("Request timed out") from exc
                except httpx.HTTPError as exc:
                    connection_exc = exc
                    continue
            else:
                raise ConnectionFailedError(
                    "Could not connect to the target server"
                ) from connection_exc

            try:
                if (
                    response.status_code in REDIRECT_STATUS_CODES
                    and "location" in response.headers
                ):
                    if redirect_count >= MAX_REDIRECTS:
                        raise TooManyRedirectsError("Too many redirects")
                    redirect_count += 1
                    location = response.headers["location"]
                    current_url = str(httpx.URL(validated.url).join(location))
                    continue

                duration_ms = (time.monotonic() - started_at) * 1000
                return HeaderInspectionResult(
                    status_code=response.status_code,
                    reason_phrase=response.reason_phrase,
                    # multi_items(), not items(): items() collapses repeated
                    # header names (e.g. two Set-Cookie headers) into one
                    # comma-joined value, which is invalid for headers whose
                    # own value can contain commas and wrong for a tool whose
                    # purpose is showing headers as the server actually sent
                    # them.
                    headers=tuple(response.headers.multi_items()),
                    final_url=validated.url,
                    redirect_count=redirect_count,
                    duration_ms=duration_ms,
                    http_version=response.http_version,
                )
            finally:
                response.close()
