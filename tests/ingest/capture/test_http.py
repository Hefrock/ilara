from __future__ import annotations

import httpx
import pytest

from ingest.capture import http as h


class FakeClock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.sleeps.append(s)
        self.t += s


def make_client(handler, clock: FakeClock | None = None) -> h.PoliteClient:
    clock = clock or FakeClock()
    limiter = h.RateLimiter(clock=clock, sleep=clock.sleep)
    return h.PoliteClient(
        transport=httpx.MockTransport(handler), limiter=limiter, sleep=clock.sleep
    )


ROBOTS_OK = "User-agent: *\nAllow: /\n"


def test_rate_limiter_fake_clock() -> None:  # T2.4
    clock = FakeClock()
    rl = h.RateLimiter(clock=clock, sleep=clock.sleep)
    times = []
    for host in ["a.gov", "a.gov", "b.gov", "a.gov"]:
        rl.wait(host)
        times.append((host, clock.t))
    a_times = [t for host, t in times if host == "a.gov"]
    assert all(b - a >= 5.0 for a, b in zip(a_times, a_times[1:], strict=False))
    assert clock.sleeps == [5.0, 5.0]  # b.gov did not wait


def test_requests_spaced_including_robots() -> None:  # T2.4 on the client
    clock = FakeClock()
    seen: list[float] = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(clock.t)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        return httpx.Response(200, text="ok")

    c = make_client(handler, clock)
    c.fetch("https://a.gov/x")
    c.fetch("https://a.gov/y")
    assert all(b - a >= 5.0 for a, b in zip(seen, seen[1:], strict=False))


def test_robots_disallow_blocks_without_body_request() -> None:  # T2.5
    paths: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        paths.append(req.url.path)
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text="User-agent: *\nDisallow: /private\n")
        return httpx.Response(200, text="secret")

    res = make_client(handler).fetch("https://a.gov/private/page")
    assert res.outcome == "blocked" and res.body is None
    assert paths == ["/robots.txt"]


@pytest.mark.parametrize(
    "status,body", [(403, "no"), (429, "slow down"), (200, "<title>Just a moment...</title>")]
)
def test_blocked_no_retry(status: int, body: str) -> None:  # T2.6
    calls: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        calls.append(req.url.path)
        return httpx.Response(status, text=body)

    res = make_client(handler).fetch("https://a.gov/page")
    assert res.outcome == "blocked" and res.body is None
    assert len(calls) == 1


def test_5xx_retried_twice_then_failed() -> None:  # T2.6
    calls: list[str] = []
    clock = FakeClock()

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        calls.append(req.url.path)
        return httpx.Response(503)

    res = make_client(handler, clock).fetch("https://a.gov/page")
    assert res.outcome == "failed" and len(calls) == 3 and res.attempts == 3
    assert 10.0 in clock.sleeps and 30.0 in clock.sleeps


def test_timeout_then_success() -> None:
    n = {"i": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/robots.txt":
            return httpx.Response(200, text=ROBOTS_OK)
        n["i"] += 1
        if n["i"] == 1:
            raise httpx.ReadTimeout("slow", request=req)
        return httpx.Response(200, text="fine")

    res = make_client(handler).fetch("https://a.gov/page")
    assert res.outcome == "ok" and res.body == b"fine" and res.attempts == 2


def test_robots_unreachable_is_failed_not_fetched() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=req)

    res = make_client(handler).fetch("https://a.gov/page")
    assert res.outcome == "failed" and "robots" in (res.error or "")
