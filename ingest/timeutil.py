"""Time helpers: UTC everywhere, with America/New_York for source-local dates."""

from __future__ import annotations

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def utc_now() -> datetime:
    return datetime.now(UTC)


def iso_utc(ts: datetime) -> str:
    return ts.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def iso_et(ts: datetime) -> str:
    return ts.astimezone(ET).isoformat(timespec="seconds")


def stamp(ts: datetime) -> str:
    """Compact UTC stamp used in raw file names: YYYYMMDDTHHMMSSZ."""
    return ts.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def parse_utc(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)
