"""
Shared HTTP helpers for connectors.

Centralises timeouts, a small retry loop for transient network errors, a
common ``User-Agent`` header, and helpers used to translate ``httpx``
exceptions into the structured ``ConnectorError`` shape we expose to the API.
The functions here are deliberately thin — the goal is to remove the
copy-pasted ``try/except httpx.HTTPStatusError/httpx.RequestError`` block
from each connector, not to introduce a new HTTP client abstraction.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import httpx

log = logging.getLogger("bricopro.http")

USER_AGENT = "BricoproHQ/1.0 (+https://github.com/titatom/bricoprohq)"

DEFAULT_TIMEOUT = httpx.Timeout(10.0, connect=5.0)

# Network-level errors are worth retrying once or twice — they cover the
# typical "the upstream container just restarted" case. HTTPStatusError is
# intentionally NOT retried (a 500 here usually means the request itself
# triggered the failure; retries amplify that).
_RETRYABLE_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def request(
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    json_body: Any = None,
    data: Any = None,
    timeout: httpx.Timeout | float | None = None,
    retries: int = 2,
    backoff: float = 0.4,
) -> httpx.Response:
    """
    Make an HTTP request with retries on transient network errors.

    Returns the raw `httpx.Response`. Callers are still responsible for
    calling `raise_for_status()` (or interpreting non-2xx responses) — we
    don't retry on HTTP status errors because they typically need to bubble
    up to the user-facing error mapping in each connector.
    """
    effective_timeout = timeout if timeout is not None else DEFAULT_TIMEOUT
    request_headers = {"User-Agent": USER_AGENT}
    if headers:
        request_headers.update(headers)

    attempts = 0
    last_exc: BaseException | None = None
    while True:
        attempts += 1
        try:
            return httpx.request(
                method.upper(),
                url,
                headers=request_headers,
                params=params,
                json=json_body,
                data=data,
                timeout=effective_timeout,
            )
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempts > retries:
                raise
            sleep_for = backoff * (2 ** (attempts - 1))
            log.info(
                "Retrying %s %s after transient %s (attempt %d/%d, sleeping %.2fs)",
                method.upper(),
                url,
                type(exc).__name__,
                attempts,
                retries + 1,
                sleep_for,
            )
            time.sleep(sleep_for)
        except httpx.RequestError:
            raise

    # Unreachable, kept for type-checkers.
    raise last_exc  # type: ignore[misc]


def get(url: str, **kwargs) -> httpx.Response:
    return request("GET", url, **kwargs)


def post(url: str, **kwargs) -> httpx.Response:
    return request("POST", url, **kwargs)


def put(url: str, **kwargs) -> httpx.Response:
    return request("PUT", url, **kwargs)


def with_attempts(
    fn: Callable[[], httpx.Response],
    *,
    retries: int = 2,
    backoff: float = 0.4,
) -> httpx.Response:
    """
    Re-run a callable that issues an HTTP request, retrying transient network
    errors only. Useful when the call site needs to set advanced httpx kwargs
    (multipart uploads, follow_redirects=False) that the simple helper above
    does not surface.
    """
    attempts = 0
    while True:
        attempts += 1
        try:
            return fn()
        except _RETRYABLE_EXCEPTIONS as exc:
            if attempts > retries:
                raise
            sleep_for = backoff * (2 ** (attempts - 1))
            log.info(
                "Retrying callable after transient %s (attempt %d/%d, sleeping %.2fs)",
                type(exc).__name__,
                attempts,
                retries + 1,
                sleep_for,
            )
            time.sleep(sleep_for)
