"""Polite HTTP fetching (WP2c).

- robots.txt is checked before any body request; a disallow means outcome ``blocked``.
- At least ``min_interval`` seconds between requests to the same host (robots.txt included).
- 403, 429 or a challenge page means ``blocked``: stop, no retry.
- 5xx or a timeout is retried at most twice with backoff, then ``failed``.
"""

from __future__ import annotations

import time
import urllib.robotparser
from collections.abc import Callable
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx

REPO_URL = "https://github.com/Hefrock/ilara"
UA_TOKEN = f"ilara-measles-archive/0.1 (+{REPO_URL})"
USER_AGENT = f"{UA_TOKEN} unofficial independent data archive"
MIN_INTERVAL_S = 5.0
MAX_RETRIES = 2
BACKOFF_S = (10.0, 30.0)

_CHALLENGE_MARKERS = (
    b"cf-chl-",
    b"challenge-platform",
    b"Just a moment...",
    b"Attention Required! | Cloudflare",
    b"g-recaptcha",
    b"h-captcha",
    b"/_Incapsula_Resource",
    b"Request unsuccessful. Incapsula",
    b"akamai-bot",
    b"Access Denied</title>",
)


def looks_like_challenge(body: bytes) -> bool:
    head = body[:20000]
    return any(m in head for m in _CHALLENGE_MARKERS)


@dataclass
class FetchResult:
    outcome: str  # ok | blocked | failed
    url: str
    status: int | None
    body: bytes | None
    content_type: str | None
    error: str | None = None
    attempts: int = 0


class RateLimiter:
    def __init__(
        self,
        min_interval: float = MIN_INTERVAL_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.min_interval = min_interval
        self.clock = clock
        self.sleep = sleep
        self._last: dict[str, float] = {}

    def wait(self, host: str) -> None:
        last = self._last.get(host)
        if last is not None:
            gap = self.clock() - last
            if gap < self.min_interval:
                self.sleep(self.min_interval - gap)
        self._last[host] = self.clock()


class PoliteClient:
    def __init__(
        self,
        transport: httpx.BaseTransport | None = None,
        limiter: RateLimiter | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = 60.0,
    ) -> None:
        self.client = httpx.Client(
            transport=transport,
            headers={"User-Agent": USER_AGENT},
            timeout=timeout,
            follow_redirects=True,
        )
        self.limiter = limiter or RateLimiter(sleep=sleep)
        self.sleep = sleep
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}

    def close(self) -> None:
        self.client.close()

    def _robots_for(self, url: str) -> urllib.robotparser.RobotFileParser | None:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin in self._robots:
            return self._robots[origin]
        rp: urllib.robotparser.RobotFileParser | None = urllib.robotparser.RobotFileParser()
        assert rp is not None
        self.limiter.wait(parts.netloc)
        try:
            r = self.client.get(origin + "/robots.txt")
            if r.status_code in (401, 403):
                rp.disallow_all = True  # type: ignore[attr-defined]
            elif r.status_code >= 400:
                rp.allow_all = True  # type: ignore[attr-defined]
            else:
                rp.parse(r.text.splitlines())
        except httpx.HTTPError:
            # robots.txt unreachable: be conservative only for this run (no cache).
            return None
        self._robots[origin] = rp
        return rp

    def allowed(self, url: str) -> bool | None:
        rp = self._robots_for(url)
        if rp is None:
            return None
        return rp.can_fetch(USER_AGENT, url)

    def fetch(self, url: str) -> FetchResult:
        allowed = self.allowed(url)
        if allowed is False:
            return FetchResult("blocked", url, None, None, None, "disallowed by robots.txt")
        if allowed is None:
            return FetchResult("failed", url, None, None, None, "robots.txt unreachable")

        host = urlsplit(url).netloc
        attempts = 0
        last_error = ""
        last_status: int | None = None
        while attempts <= MAX_RETRIES:
            if attempts:
                self.sleep(BACKOFF_S[min(attempts - 1, len(BACKOFF_S) - 1)])
            attempts += 1
            self.limiter.wait(host)
            try:
                r = self.client.get(url)
            except httpx.TimeoutException as e:
                last_error, last_status = f"timeout: {e}", None
                continue
            except httpx.HTTPError as e:
                last_error, last_status = f"{type(e).__name__}: {e}", None
                continue
            body = r.content
            ctype = r.headers.get("content-type")
            if r.status_code in (403, 429):
                return FetchResult(
                    "blocked", url, r.status_code, None, ctype, f"HTTP {r.status_code}", attempts
                )
            if looks_like_challenge(body):
                return FetchResult(
                    "blocked", url, r.status_code, None, ctype, "challenge page detected", attempts
                )
            if r.status_code >= 500:
                last_error, last_status = f"HTTP {r.status_code}", r.status_code
                continue
            if r.status_code >= 400:
                return FetchResult(
                    "failed", url, r.status_code, None, ctype, f"HTTP {r.status_code}", attempts
                )
            return FetchResult("ok", str(r.url), r.status_code, body, ctype, None, attempts)
        return FetchResult("failed", url, last_status, None, None, last_error, attempts)
