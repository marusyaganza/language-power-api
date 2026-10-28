"""Only accept requests that came through the frontend's Netlify proxy.

The frontend proxies `/api/*` to this API with Netlify's `signed` option: every
forwarded request carries an `X-Nf-Sign` header holding a JWS (a JWT signed
with HS256) made with a secret shared by Netlify and this API. A request
without a valid one did not come through the frontend, for example a direct
call to the Cloud Run URL, and is rejected.

The check is off while `settings.proxy_signature_secret` is unset, as in local
development (the Vite dev proxy doesn't sign) and in tests.

Netlify also tells the API who the visitor is (`client_ip`), for per-IP limits.
"""

import ipaddress

import jwt
from fastapi import HTTPException, Request, status

from settings import settings

SIGNATURE_HEADER = "x-nf-sign"
NETLIFY_ISSUER = "netlify"
CLIENT_IP_HEADER = "x-nf-client-connection-ip"


async def require_proxy_signature(request: Request) -> None:
    """Reject the request unless its signature header is valid.

    Valid means: signed with HS256 and the shared secret, issued by Netlify,
    and not expired if the token has an expiry. The header is read from the
    request rather than declared as a parameter, so it doesn't appear on every
    route in the API docs.

    Raises:
        HTTPException: 403 if the header is missing or invalid. The detail
            differs from "Not authenticated", so a misconfigured proxy isn't
            mistaken for a logged-out user.
    """
    secret = settings.proxy_signature_secret
    if secret is None:
        return

    token = request.headers.get(SIGNATURE_HEADER)
    try:
        if token is None:
            raise jwt.InvalidTokenError("missing")
        jwt.decode(
            token,
            secret.get_secret_value(),
            algorithms=["HS256"],
            issuer=NETLIFY_ISSUER,
            options={"require": ["iss"]},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Request did not come through the frontend proxy",
        ) from exc


def client_ip(request: Request) -> str | None:
    """The visitor's IP address as Netlify saw it, for per-IP limits; None where it isn't known.

    Netlify sets `X-Nf-Client-Connection-Ip` on every request it forwards. The
    header is only trusted while signatures are checked: without the check,
    anyone can call the API directly and put any address in it. Never
    `X-Forwarded-For`, which the client can partly write.

    An IPv6 address becomes its /64 network, which usually belongs to one
    home or device, so its owner can't get fresh limits by changing the last
    bits. A value that isn't an address is used as it is.
    """
    if settings.proxy_signature_secret is None:
        return None
    value = request.headers.get(CLIENT_IP_HEADER)
    if not value:
        return None
    try:
        address = ipaddress.ip_address(value.strip())
    except ValueError:
        return value
    if address.version == 6:
        return str(ipaddress.ip_network((address, 64), strict=False))
    return str(address)
