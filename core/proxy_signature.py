"""Only accept requests that came through the frontend's Netlify proxy.

The frontend proxies `/api/*` to this API with Netlify's `signed` option: every
forwarded request carries an `X-Nf-Sign` header holding a JWS (a JWT signed
with HS256) made with a secret shared by Netlify and this API. A request
without a valid one did not come through the frontend, for example a direct
call to the Cloud Run URL, and is rejected.

The check is off while `settings.proxy_signature_secret` is unset, as in local
development (the Vite dev proxy doesn't sign) and in tests.
"""
import jwt
from fastapi import HTTPException, Request, status

from settings import settings

SIGNATURE_HEADER = "x-nf-sign"
NETLIFY_ISSUER = "netlify"


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
