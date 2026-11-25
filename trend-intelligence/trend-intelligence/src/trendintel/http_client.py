"""A polite HTTP client.

Purpose: every collector goes through this class so that request hygiene is
enforced in one place: identifying User-Agent, timeouts, bounded retries with
exponential back-off (honouring Retry-After), and a minimum interval between
requests to the same host so we never hammer a source.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable
from urllib.parse import urlsplit

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


class HttpError(RuntimeError):
    """A request failed after retries, or returned an error status / invalid body."""


class PoliteHttpClient:
    def __init__(
        self,
        user_agent: str,
        timeout: float = 15.0,
        min_interval: float = 1.0,
        max_retries: int = 3,
        backoff_factor: float = 1.0,
        session: Any | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.timeout = timeout
        self.min_interval = min_interval
        self._clock = clock
        self._sleep = sleep
        self._last_call: dict[str, float] = {}

        if session is None:
            session = requests.Session()
            retry = Retry(
                total=max_retries,
                connect=max_retries,
                read=max_retries,
                status=max_retries,
                backoff_factor=backoff_factor,
                status_forcelist=(429, 500, 502, 503, 504),
                allowed_methods=frozenset({"GET", "POST"}),
                respect_retry_after_header=True,
                raise_on_status=False,
            )
            adapter = HTTPAdapter(max_retries=retry)
            session.mount("https://", adapter)
            session.mount("http://", adapter)
        session.headers.update(
            {"User-Agent": user_agent, "Accept": "application/json, application/xml;q=0.9, */*;q=0.8"}
        )
        self.session = session

    @classmethod
    def from_settings(cls, settings: Any) -> "PoliteHttpClient":
        return cls(
            user_agent=settings.user_agent,
            timeout=settings.request_timeout,
            min_interval=settings.request_min_interval,
            max_retries=settings.max_retries,
        )

    def _throttle(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_call.get(host)
        if last is not None:
            wait = self.min_interval - (self._clock() - last)
            if wait > 0:
                logger.debug("Throttling %.2fs before calling %s", wait, host)
                self._sleep(wait)
        self._last_call[host] = self._clock()

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        self._throttle(url)
        kwargs.setdefault("timeout", self.timeout)
        logger.debug("%s %s", method, url)
        try:
            response = self.session.request(method, url, **kwargs)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise HttpError(f"{method} {url} failed: {exc}") from exc
        return response

    def get(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> requests.Response:
        return self.request("POST", url, **kwargs)

    @staticmethod
    def _json(response: requests.Response, url: str) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise HttpError(f"Invalid JSON returned by {url}") from exc

    def get_json(self, url: str, **kwargs: Any) -> Any:
        return self._json(self.get(url, **kwargs), url)

    def post_json(self, url: str, **kwargs: Any) -> Any:
        return self._json(self.post(url, **kwargs), url)
