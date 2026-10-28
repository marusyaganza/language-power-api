"""The visitor's IP from Netlify's header, trusted only behind the signature check."""

import pytest
from pydantic import SecretStr
from starlette.requests import Request

from core.proxy_signature import client_ip
from settings import settings


def request(**headers: str) -> Request:
    raw = [(name.replace("_", "-").encode(), value.encode()) for name, value in headers.items()]
    return Request({"type": "http", "headers": raw})


@pytest.fixture
def signed(monkeypatch):
    monkeypatch.setattr(settings, "proxy_signature_secret", SecretStr("secret"))


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("203.0.113.7", "203.0.113.7"),
        (" 203.0.113.7 ", "203.0.113.7"),
        ("2001:db8:1:2:3:4:5:6", "2001:db8:1:2::/64"),
        ("2001:db8:1:2:ffff::1", "2001:db8:1:2::/64"),
        ("not-an-ip", "not-an-ip"),
    ],
    ids=["ipv4", "spaces", "ipv6", "same-ipv6-network", "not-an-address"],
)
def test_reads_netlifys_header(signed, header, expected):
    assert client_ip(request(x_nf_client_connection_ip=header)) == expected


def test_unknown_without_the_header(signed):
    assert client_ip(request()) is None


def test_never_reads_x_forwarded_for(signed):
    assert client_ip(request(x_forwarded_for="203.0.113.7")) is None


def test_untrusted_without_the_signature_check():
    assert settings.proxy_signature_secret is None
    assert client_ip(request(x_nf_client_connection_ip="203.0.113.7")) is None
