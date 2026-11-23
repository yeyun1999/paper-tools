"""HTTP client wrapper: per-host rate limiting, retry with backoff, response cache."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx

from paper_tools import __version__
from paper_tools.core.cache import Cache
from paper_tools.core.errors import UpstreamError

logger = logging.getLogger(__name__)

DEFAULT_RATE_LIMITS: dict[str, float] = {
    "eutils.ncbi.nlm.nih.gov": 3.0,
    "www.ncbi.nlm.nih.gov": 3.0,
    "ftp.ncbi.nlm.nih.gov": 3.0,
    "www.ebi.ac.uk": 3.0,
    "api.crossref.org": 5.0,
    "api.openalex.org": 5.0,
    "api.semanticscholar.org": 1.0,
    "api.unpaywall.org": 5.0,
}

_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRY_AFTER = 60.0


class HttpClient:
    def __init__(
        self,
        *,
        timeout: float = 30.0,
        mailto: str | None = None,
        cache: Cache | None = None,
        rate_limits: dict[str, float] | None = None,
        max_retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
        client: httpx.Client | None = None,
    ) -> None:
        ua = f"paper-tools/{__version__}" + (f" (+{mailto})" if mailto else "")
        if client is not None:
            self._client = client
        else:
            try:
                self._client = httpx.Client(
                    timeout=timeout, headers={"User-Agent": ua}, follow_redirects=True
                )
            except httpx.InvalidURL:
                # e.g. NO_PROXY containing bare IPv6 literals breaks httpx env parsing
                logger.warning("Malformed proxy environment variables; ignoring env proxies")
                self._client = httpx.Client(
                    timeout=timeout,
                    headers={"User-Agent": ua},
                    follow_redirects=True,
                    trust_env=False,
                )
        self._cache = cache
        self._rates = {**DEFAULT_RATE_LIMITS, **(rate_limits or {})}
        self._max_retries = max_retries
        self._sleep = sleep
        self._last_request: dict[str, float] = {}

    def set_rate_limit(self, host: str, requests_per_second: float) -> None:
        """Plugins may raise a host's rate limit when authenticated (e.g. NCBI api_key)."""
        self._rates[host] = requests_per_second

    def _throttle(self, host: str) -> None:
        rate = self._rates.get(host)
        if not rate:
            return
        interval = 1.0 / rate
        now = time.monotonic()
        last = self._last_request.get(host)
        if last is not None:
            wait = interval - (now - last)
            if wait > 0:
                self._sleep(wait)
        self._last_request[host] = time.monotonic()

    def _backoff(self, attempt: int, response: httpx.Response | None) -> float:
        if response is not None:
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    return min(float(retry_after), _MAX_RETRY_AFTER)
                except ValueError:
                    pass
        return 0.5 * (2.0**attempt) + random.uniform(0, 0.25)

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        cache_ttl: float | None = None,
    ) -> httpx.Response:
        host = urlparse(url).hostname or ""
        body_sig = ""
        if json_body is not None:
            body_sig = hashlib.sha256(json.dumps(json_body, sort_keys=True).encode()).hexdigest()
        elif data is not None:
            body_sig = hashlib.sha256(urlencode(sorted(data.items())).encode()).hexdigest()
        cache_key = f"http:{method}:{url}:{urlencode(sorted((params or {}).items()))}"
        if body_sig:
            cache_key += f":{body_sig}"
        cacheable = method in {"GET", "POST"} and cache_ttl is not None and self._cache is not None
        if cacheable and self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return httpx.Response(200, content=cached, request=httpx.Request(method, url))

        last_exc: Exception | None = None
        last_status: int | None = None
        for attempt in range(self._max_retries):
            self._throttle(host)
            response: httpx.Response | None = None
            try:
                response = self._client.request(
                    method,
                    url,
                    params=params,
                    headers=headers,
                    json=json_body,
                    data=data,
                )
            except httpx.TransportError as exc:
                last_exc = exc
                logger.debug("transport error on %s (attempt %d): %s", url, attempt + 1, exc)
            if response is not None:
                last_status = response.status_code
            if response is not None and response.status_code not in _RETRY_STATUSES:
                if response.status_code >= 400:
                    raise UpstreamError(
                        f"HTTP {response.status_code} from {host}",
                        url=url,
                        status=response.status_code,
                    )
                if cacheable and self._cache is not None:
                    self._cache.set(cache_key, response.content, ttl=cache_ttl)
                return response
            if attempt < self._max_retries - 1:
                delay = self._backoff(attempt, response)
                logger.debug("retrying %s in %.2fs (attempt %d)", url, delay, attempt + 1)
                self._sleep(delay)
        details: dict[str, Any] = {"url": url}
        if last_status is not None:
            details["status"] = last_status
        raise UpstreamError(
            f"Request to {host} failed after {self._max_retries} attempts",
            **details,
        ) from last_exc

    def get_json(
        self,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: float | None = None,
    ) -> Any:
        response = self.request("GET", url, params=params, headers=headers, cache_ttl=cache_ttl)
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("Invalid JSON response", url=url) from exc

    def get_bytes(self, url: str, *, params: dict[str, Any] | None = None) -> bytes:
        return self.request("GET", url, params=params).content

    def post_json(
        self,
        url: str,
        *,
        json_body: dict[str, Any] | None = None,
        data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        cache_ttl: float | None = None,
    ) -> Any:
        """POST a JSON (or form) body and parse the JSON response.

        Caching is opt-in via cache_ttl (for idempotent query APIs); the cache
        key includes a hash of the request body, so different bodies never collide.
        """
        response = self.request(
            "POST",
            url,
            params=params,
            headers=headers,
            json_body=json_body,
            data=data,
            cache_ttl=cache_ttl,
        )
        try:
            return response.json()
        except ValueError as exc:
            raise UpstreamError("Invalid JSON response", url=url) from exc
