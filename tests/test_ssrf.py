import socket
from ipaddress import ip_address

import pytest

from app.ssrf import (
    SSRFValidationError,
    ValidatedUrl,
    is_blocked_ip,
    resolve_and_validate_host,
    validate_public_url,
    validate_scheme_and_host,
)


class TestIsBlockedIp:
    @pytest.mark.parametrize(
        "ip",
        [
            "127.0.0.1",  # loopback
            "127.255.255.255",
            "10.0.0.1",  # private
            "172.16.0.1",
            "172.31.255.255",
            "192.168.1.1",
            "169.254.169.254",  # link-local / cloud metadata endpoint
            "169.254.0.1",
            "224.0.0.1",  # multicast
            "240.0.0.1",  # reserved
            "0.0.0.0",  # unspecified
            "::1",  # loopback v6
            "fc00::1",  # unique local v6
            "fe80::1",  # link-local v6
            "ff02::1",  # multicast v6
            "100.64.0.1",  # CGNAT (RFC 6598) - not is_private, but not is_global either
            "100.100.100.100",
            "100.127.255.255",  # top of the 100.64.0.0/10 range
        ],
    )
    def test_blocks_private_and_special_ips(self, ip):
        assert is_blocked_ip(ip_address(ip)) is True

    @pytest.mark.parametrize(
        "ip",
        ["8.8.8.8", "1.1.1.1", "93.184.216.34", "2606:4700:4700::1111"],
    )
    def test_allows_public_ips(self, ip):
        assert is_blocked_ip(ip_address(ip)) is False


class TestValidateSchemeAndHost:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("http://example.com", ("http", "example.com", 80)),
            ("https://example.com", ("https", "example.com", 443)),
            ("https://example.com:8443/path?query=1", ("https", "example.com", 8443)),
            ("http://example.com:8080", ("http", "example.com", 8080)),
        ],
    )
    def test_accepts_valid_http_https_urls(self, url, expected):
        assert validate_scheme_and_host(url) == expected

    @pytest.mark.parametrize(
        "url",
        [
            "ftp://example.com",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "example.com",
            "",
            "http://",
            "http:///path",
            "http://example.com:not-a-port",
        ],
    )
    def test_rejects_invalid_urls(self, url):
        with pytest.raises(SSRFValidationError) as exc_info:
            validate_scheme_and_host(url)
        assert exc_info.value.code == "INVALID_URL"

    def test_does_not_touch_network(self, mocker):
        spy = mocker.patch("app.ssrf.socket.getaddrinfo")
        with pytest.raises(SSRFValidationError):
            validate_scheme_and_host("ftp://example.com")
        spy.assert_not_called()


class TestResolveAndValidateHost:
    @staticmethod
    def _addrinfo(*ips: str, port: int = 80):
        return [
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (ip, port))
            for ip in ips
        ]

    def test_returns_ips_when_all_public(self, mocker):
        # Order is preserved from getaddrinfo (resolver preference), not
        # sorted alphabetically as a string.
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=self._addrinfo("8.8.8.8", "1.1.1.1"),
        )
        assert resolve_and_validate_host("example.com", 80) == ("8.8.8.8", "1.1.1.1")

    def test_raises_when_resolved_ip_is_blocked(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=self._addrinfo("127.0.0.1"),
        )
        with pytest.raises(SSRFValidationError) as exc_info:
            resolve_and_validate_host("localhost", 80)
        assert exc_info.value.code == "BLOCKED_URL"

    def test_raises_when_any_resolved_ip_is_blocked(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=self._addrinfo("8.8.8.8", "169.254.169.254"),
        )
        with pytest.raises(SSRFValidationError) as exc_info:
            resolve_and_validate_host("example.com", 80)
        assert exc_info.value.code == "BLOCKED_URL"

    def test_raises_when_dns_resolution_fails(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            side_effect=socket.gaierror("Name or service not known"),
        )
        with pytest.raises(SSRFValidationError) as exc_info:
            resolve_and_validate_host("does-not-exist.invalid", 80)
        assert exc_info.value.code == "CONNECTION_ERROR"

    def test_raises_connection_error_not_unhandled_exception_on_overlong_label(self):
        # Real repro, no mocking: an absurdly long hostname label makes the
        # stdlib's IDNA encoder raise UnicodeError inside socket.getaddrinfo
        # before any lookup is attempted. This must be treated the same as a
        # DNS resolution failure, not propagate as an unhandled exception.
        hostname = "a" * 300 + ".com"
        with pytest.raises(SSRFValidationError) as exc_info:
            resolve_and_validate_host(hostname, 80)
        assert exc_info.value.code == "CONNECTION_ERROR"

    def test_orders_ipv4_before_ipv6_preserving_resolver_order_and_dedupes(
        self, mocker
    ):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=[
                (
                    socket.AF_INET6,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("2606:4700:4700::1111", 80, 0, 0),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 80),
                ),
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.35", 80),
                ),
                # Duplicate of the first IPv4 entry above (e.g. TCP+UDP both
                # resolving to the same address) must not appear twice.
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("93.184.216.34", 80),
                ),
            ],
        )
        assert resolve_and_validate_host("dualstack.example.com", 80) == (
            "93.184.216.34",
            "93.184.216.35",
            "2606:4700:4700::1111",
        )


class TestValidatePublicUrl:
    def test_returns_validated_url_for_safe_public_url(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=TestResolveAndValidateHost._addrinfo("8.8.8.8"),
        )
        result = validate_public_url("https://example.com/path")
        assert result == ValidatedUrl(
            url="https://example.com/path",
            scheme="https",
            hostname="example.com",
            port=443,
            resolved_ips=("8.8.8.8",),
        )

    def test_rejects_disallowed_scheme_without_dns_lookup(self, mocker):
        spy = mocker.patch("app.ssrf.socket.getaddrinfo")
        with pytest.raises(SSRFValidationError) as exc_info:
            validate_public_url("ftp://example.com")
        assert exc_info.value.code == "INVALID_URL"
        spy.assert_not_called()

    def test_rejects_url_resolving_to_private_ip(self, mocker):
        mocker.patch(
            "app.ssrf.socket.getaddrinfo",
            return_value=TestResolveAndValidateHost._addrinfo("10.0.0.5"),
        )
        with pytest.raises(SSRFValidationError) as exc_info:
            validate_public_url("http://internal.example.com")
        assert exc_info.value.code == "BLOCKED_URL"
