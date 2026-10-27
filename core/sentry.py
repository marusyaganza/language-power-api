"""Error reporting to Sentry, with personal data and secrets kept out.

Off unless `settings.sentry_dsn` is set, so local runs and tests send nothing.
When on, Sentry reports unhandled exceptions, 5xx responses and
`logger.exception`/`logger.error` calls; warnings become breadcrumbs on the
next event. Tracing is off.

Sentry's own personal data setting stays at its default, off (no user IPs,
cookies or auth headers). That is not enough on its own for this app; every
option below closes a specific leak:

* Request bodies hold emails, passwords and saved words: never sent.
* Local variables in stack frames hold the same, and the Merriam-Webster key
  (`params={"key": ...}`): never sent. Sentry's scrubber only matches certain
  variable names, and `key` and `email` aren't among them.
* Redis breadcrumbs record each command's key, such as `session:<id>`, a
  working login token: the Redis integration is off.
* The `httpx` breadcrumb of a dictionary lookup records the query string,
  which holds the MW key: removed by `scrub_breadcrumb`.
* Netlify adds headers with the proxy signature, the client's IP and its
  location: only the headers in `_KEPT_HEADERS` are sent (`scrub_event`).
"""

from typing import Any

import sentry_sdk
from sentry_sdk.integrations.redis import RedisIntegration

from settings import Settings

__all__ = ["sentry_options", "init_sentry", "scrub_event", "scrub_breadcrumb"]

# Request headers sent with an event; every other header is dropped. An
# allowlist rather than a denylist, so a header added later (by Netlify or
# anything else) is never sent by default.
_KEPT_HEADERS = frozenset({"accept", "content-length", "content-type", "user-agent"})


def scrub_event(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """`before_send`: keep only the request headers in `_KEPT_HEADERS`."""
    request = event.get("request")
    if isinstance(request, dict) and isinstance(request.get("headers"), dict):
        request["headers"] = {
            name: value for name, value in request["headers"].items() if name.lower() in _KEPT_HEADERS
        }
    return event


def scrub_breadcrumb(crumb: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    """`before_breadcrumb`: drop the query string of outgoing HTTP requests.

    The URL itself is kept (without its query string, as Sentry records it).
    """
    data = crumb.get("data")
    if isinstance(data, dict):
        data.pop("http.query", None)
    return crumb


def sentry_options(settings: Settings) -> dict[str, Any] | None:
    """The `sentry_sdk.init` options for these settings, or None if Sentry is off."""
    dsn = settings.sentry_dsn.get_secret_value() if settings.sentry_dsn else ""
    if not dsn:
        return None
    return {
        "dsn": dsn,
        "environment": settings.sentry_environment,
        "release": settings.sentry_release or None,
        "max_request_body_size": "never",
        "include_local_variables": False,
        "disabled_integrations": [RedisIntegration()],
        "before_send": scrub_event,
        "before_breadcrumb": scrub_breadcrumb,
    }


def init_sentry(settings: Settings) -> bool:
    """Start reporting to Sentry if a DSN is set. Returns whether it started.

    Call it before the FastAPI app is created.
    """
    options = sentry_options(settings)
    if options is None:
        return False
    sentry_sdk.init(**options)
    return True
