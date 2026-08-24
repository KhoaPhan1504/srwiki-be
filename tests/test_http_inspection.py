import socket

import httpx
import pytest

from app.http_inspection import (
    MAX_REDIRECTS,
    REQUEST_TIMEOUT_SECONDS,
    BlockedUrlError,
    ConnectionFailedError,
    InvalidUrlError,
    RequestTimedOutError,
    TooManyRedirectsError,
    inspect_headers,
)


def _addrinfo(ip: str, port: int):
    return [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))]


def _mock_dns(mocker, hostname_to_ip: dict[str, str]):
    def fake_getaddrinfo(host, port, **kwargs):
        try:
            ip = hostname_to_ip[host]
        except KeyError:
            raise socket.gaierror(f"no mock DNS entry for {host}")
        return _addrinfo(ip, port)

    return mocker.patch("app.ssrf.socket.getaddrinfo", side_effect=fake_getaddrinfo)


class TestInspectHeadersSuccess:
    def test_returns_status_headers_and_metadata_for_200(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["host"] == "example.com"
            assert request.extensions["sni_hostname"] == "example.com"
            assert request.url.host == "93.184.216.34"
            return httpx.Response(
                200,
                headers={"content-type": "application/json", "x-custom": "abc"},
            )

        result = inspect_headers(
            "https://example.com/api", transport=httpx.MockTransport(handler)
        )

        assert result.status_code == 200
        assert result.reason_phrase == "OK"
        assert dict(result.headers) == {
            "content-type": "application/json",
            "x-custom": "abc",
        }
        assert result.final_url == "https://example.com/api"
        assert result.redirect_count == 0
        assert result.http_version == "HTTP/1.1"
        assert result.duration_ms >= 0

    def test_non_2xx_status_is_still_a_success_result(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})
        handler = httpx.MockTransport(lambda request: httpx.Response(404))

        result = inspect_headers("https://example.com/missing", transport=handler)

        assert result.status_code == 404
        assert result.redirect_count == 0

    def test_preserves_duplicate_response_headers_separately(self, mocker):
        # Regression test at the inspect_headers() level: a router-layer test
        # asserts this property too, but it mocks inspect_headers itself and
        # hand-feeds an already-separated tuple, so it can't catch a bug in
        # how inspect_headers extracts headers from the httpx response. This
        # one exercises the real extraction code via a MockTransport response
        # carrying two headers with the same name (httpx.Headers.items()
        # would collapse these into one comma-joined value).
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers=[
                    ("set-cookie", "a=1; Path=/"),
                    ("set-cookie", "b=2; Path=/"),
                ],
            )

        result = inspect_headers(
            "https://example.com/", transport=httpx.MockTransport(handler)
        )

        assert result.headers == (
            ("set-cookie", "a=1; Path=/"),
            ("set-cookie", "b=2; Path=/"),
        )

    def test_includes_non_default_port_in_host_header(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            assert request.headers["host"] == "example.com:8443"
            assert request.url.host == "93.184.216.34"
            assert request.url.port == 8443
            return httpx.Response(200)

        inspect_headers(
            "https://example.com:8443/x", transport=httpx.MockTransport(handler)
        )

    def test_does_not_read_response_body(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})
        read_calls = {"n": 0}

        class TrackingTransport(httpx.MockTransport):
            def handle_request(self, request):
                response = super().handle_request(request)
                original_read = response.read

                def tracked_read():
                    read_calls["n"] += 1
                    return original_read()

                response.read = tracked_read
                return response

        transport = TrackingTransport(
            lambda request: httpx.Response(200, content=b"x" * 1000)
        )
        inspect_headers("https://example.com/big", transport=transport)

        assert read_calls["n"] == 0


class TestInspectHeadersRedirects:
    def test_follows_redirect_and_reports_final_url(self, mocker):
        _mock_dns(
            mocker,
            {"a.example.com": "93.184.216.10", "b.example.com": "93.184.216.20"},
        )

        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers["host"] == "a.example.com":
                return httpx.Response(
                    302, headers={"location": "https://b.example.com/final"}
                )
            return httpx.Response(200, headers={"x-final": "yes"})

        result = inspect_headers(
            "https://a.example.com/start", transport=httpx.MockTransport(handler)
        )

        assert result.status_code == 200
        assert result.final_url == "https://b.example.com/final"
        assert result.redirect_count == 1
        assert dict(result.headers) == {"x-final": "yes"}

    def test_resolves_relative_location_against_current_host(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/start":
                return httpx.Response(301, headers={"location": "/next"})
            return httpx.Response(200)

        result = inspect_headers(
            "https://example.com/start", transport=httpx.MockTransport(handler)
        )

        assert result.final_url == "https://example.com/next"
        assert result.redirect_count == 1

    def test_revalidates_every_redirect_hop_and_blocks_ssrf_via_redirect(self, mocker):
        _mock_dns(
            mocker,
            {"public.example.com": "93.184.216.10", "internal.example.com": "10.0.0.5"},
        )
        handler = httpx.MockTransport(
            lambda request: httpx.Response(
                302, headers={"location": "https://internal.example.com/steal"}
            )
        )

        with pytest.raises(BlockedUrlError):
            inspect_headers("https://public.example.com/start", transport=handler)

    def test_raises_too_many_redirects_beyond_the_limit(self, mocker):
        _mock_dns(mocker, {f"h{i}.example.com": f"93.184.216.{i}" for i in range(20)})

        def handler(request: httpx.Request) -> httpx.Response:
            current_host = request.headers["host"]
            index = int(current_host.removeprefix("h").split(".")[0])
            next_host = f"h{index + 1}.example.com"
            return httpx.Response(302, headers={"location": f"https://{next_host}/"})

        with pytest.raises(TooManyRedirectsError):
            inspect_headers(
                "https://h0.example.com/", transport=httpx.MockTransport(handler)
            )

    def test_allows_exactly_max_redirects_hops(self, mocker):
        _mock_dns(mocker, {f"h{i}.example.com": f"93.184.216.{i}" for i in range(20)})

        def handler(request: httpx.Request) -> httpx.Response:
            current_host = request.headers["host"]
            index = int(current_host.removeprefix("h").split(".")[0])
            if index >= MAX_REDIRECTS:
                return httpx.Response(200)
            next_host = f"h{index + 1}.example.com"
            return httpx.Response(302, headers={"location": f"https://{next_host}/"})

        result = inspect_headers(
            "https://h0.example.com/", transport=httpx.MockTransport(handler)
        )

        assert result.status_code == 200
        assert result.redirect_count == MAX_REDIRECTS


class TestInspectHeadersErrors:
    def test_invalid_url_raises_invalid_url_error(self, mocker):
        spy = mocker.patch("app.ssrf.socket.getaddrinfo")
        with pytest.raises(InvalidUrlError):
            inspect_headers(
                "ftp://example.com",
                transport=httpx.MockTransport(lambda r: httpx.Response(200)),
            )
        spy.assert_not_called()

    def test_blocked_url_raises_blocked_url_error(self, mocker):
        _mock_dns(mocker, {"internal.example.com": "127.0.0.1"})
        with pytest.raises(BlockedUrlError):
            inspect_headers(
                "http://internal.example.com/",
                transport=httpx.MockTransport(lambda r: httpx.Response(200)),
            )

    def test_dns_failure_raises_connection_failed_error(self, mocker):
        _mock_dns(mocker, {})
        with pytest.raises(ConnectionFailedError):
            inspect_headers(
                "http://does-not-exist.invalid/",
                transport=httpx.MockTransport(lambda r: httpx.Response(200)),
            )

    def test_transport_timeout_raises_request_timed_out_error(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectTimeout("timed out", request=request)

        with pytest.raises(RequestTimedOutError):
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

    def test_transport_connect_error_raises_connection_failed_error(self, mocker):
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(ConnectionFailedError):
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

    def test_connection_failed_error_message_is_a_fixed_generic_string(self, mocker):
        # Not the raw httpx exception text (which can leak internal detail,
        # e.g. "Invalid URL in location header: ..."), for defense in depth
        # and consistency with the other HeaderInspectionError subclasses.
        _mock_dns(mocker, {"example.com": "93.184.216.34"})

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError(
                "some very specific internal detail", request=request
            )

        with pytest.raises(ConnectionFailedError) as exc_info:
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

        assert "some very specific internal detail" not in exc_info.value.message
        assert exc_info.value.message == "Could not connect to the target server"


class TestInspectHeadersMultiIpFallback:
    def test_falls_back_to_next_resolved_ip_when_first_connection_fails(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 443),
                ),
            ],
        )
        attempted_hosts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempted_hosts.append(request.url.host)
            if request.url.host == "93.184.216.34":
                raise httpx.ConnectError("connection refused", request=request)
            return httpx.Response(200, headers={"x-served-by": "second-ip"})

        result = inspect_headers(
            "https://example.com/", transport=httpx.MockTransport(handler)
        )

        assert attempted_hosts == ["93.184.216.34", "93.184.216.35"]
        assert result.status_code == 200
        assert dict(result.headers) == {"x-served-by": "second-ip"}

    def test_raises_connection_failed_only_when_every_candidate_ip_fails(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 443),
                ),
            ],
        )

        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(ConnectionFailedError):
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

    def test_timeout_on_first_candidate_raises_immediately_without_trying_others(
        self, mocker
    ):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 443),
                ),
            ],
        )
        attempted_hosts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempted_hosts.append(request.url.host)
            raise httpx.ConnectTimeout("timed out", request=request)

        with pytest.raises(RequestTimedOutError):
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

        # A timeout on one candidate isn't evidence the others would fail
        # faster - it must not be retried against the remaining candidates.
        assert attempted_hosts == ["93.184.216.34"]

    def test_recomputes_remaining_timeout_before_each_candidate_ip(self, mocker):
        # Three candidates for one hop: the first two fail with a
        # non-timeout HTTPError (e.g. connection refused), so the loop
        # falls through to a third. Each attempt should get a freshly
        # recomputed "remaining" budget - not the same snapshot taken once
        # at the top of the hop - so the timeout passed to each subsequent
        # candidate must be strictly smaller than the one before it.
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.36", 443),
                ),
            ],
        )

        # Call 1 = started_at (0.0). Every call after that advances by 2s
        # of simulated elapsed time, deterministically modelling each
        # failed connection attempt burning into the total budget.
        elapsed = {"value": 0.0}

        def fake_monotonic():
            current = elapsed["value"]
            elapsed["value"] += 2.0
            return current

        mocker.patch("app.http_inspection.time.monotonic", side_effect=fake_monotonic)

        seen_timeouts = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_timeouts.append(request.extensions["timeout"]["connect"])
            if request.url.host == "93.184.216.36":
                return httpx.Response(200)
            raise httpx.ConnectError("connection refused", request=request)

        result = inspect_headers(
            "https://example.com/", transport=httpx.MockTransport(handler)
        )

        assert result.status_code == 200
        assert len(seen_timeouts) == 3
        # Strictly decreasing, not the same value reused for all three.
        assert seen_timeouts[0] > seen_timeouts[1] > seen_timeouts[2]
        assert seen_timeouts == [8.0, 6.0, 4.0]

    def test_raises_timed_out_when_budget_exhausted_partway_through_candidates(
        self, mocker
    ):
        # Same three-candidate setup, but the simulated elapsed time jumps
        # straight past the total budget after the first candidate fails.
        # The second candidate's freshly-recomputed remaining budget must
        # be <= 0, so it must raise immediately rather than being attempted
        # with an expired (or negative) timeout.
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 443),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.36", 443),
                ),
            ],
        )

        call_count = {"n": 0}

        def fake_monotonic():
            call_count["n"] += 1
            # Call 1 = started_at, call 2 = remaining check before the
            # first candidate (well inside budget). From then on, every
            # call simulates that the first candidate's failed attempt
            # alone already consumed the whole budget.
            if call_count["n"] <= 2:
                return 0.0
            return REQUEST_TIMEOUT_SECONDS + 1.0

        mocker.patch("app.http_inspection.time.monotonic", side_effect=fake_monotonic)

        attempted_hosts = []

        def handler(request: httpx.Request) -> httpx.Response:
            attempted_hosts.append(request.url.host)
            raise httpx.ConnectError("connection refused", request=request)

        with pytest.raises(RequestTimedOutError):
            inspect_headers(
                "https://example.com/", transport=httpx.MockTransport(handler)
            )

        # Only the first candidate was ever attempted - the second
        # candidate's remaining budget was already <= 0, so it must not
        # be attempted at all.
        assert attempted_hosts == ["93.184.216.34"]


class TestInspectHeadersTimeoutBudget:
    def test_enforces_total_time_budget_across_redirect_hops_not_per_hop(self, mocker):
        _mock_dns(
            mocker,
            {"a.example.com": "93.184.216.10", "b.example.com": "93.184.216.20"},
        )

        call_count = {"n": 0}

        def fake_monotonic():
            call_count["n"] += 1
            # Call 1 is started_at, call 2 is the hop-1 remaining check
            # (well inside budget); every call from then on simulates that
            # hop 1's request alone already consumed the whole budget, so
            # the hop-2 remaining check must trip immediately.
            if call_count["n"] <= 2:
                return 0.0
            return REQUEST_TIMEOUT_SECONDS + 1.0

        mocker.patch("app.http_inspection.time.monotonic", side_effect=fake_monotonic)

        hop2_was_sent = {"value": False}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.headers["host"] == "a.example.com":
                return httpx.Response(
                    302, headers={"location": "https://b.example.com/final"}
                )
            hop2_was_sent["value"] = True
            return httpx.Response(200)

        with pytest.raises(RequestTimedOutError):
            inspect_headers(
                "https://a.example.com/start", transport=httpx.MockTransport(handler)
            )

        assert hop2_was_sent["value"] is False
