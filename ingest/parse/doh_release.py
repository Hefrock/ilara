"""Parser for DOH newsroom releases (WP3c backfill, sources S1).

A release's ``as_of_date`` is its dateline date ("August 31, 2026  Harrisburg, PA –"): the text
says "today announced". Statewide figures come from the "Key updates" block when present
(new cases since a date, total counties, cumulative cases, hospitalizations, deaths,
vaccinated cases), else from the headline sentence. "so far in 2026" / "in 2026" marks a
calendar-year count; anything else is ``unknown``. Releases without statewide figures (for
example exposure notices) produce no case rows. Only numbers are stored, never release text
(I10).
"""

from __future__ import annotations

import html as htmlmod
import re
from datetime import date, datetime
from typing import Any

PARSER_VERSION = "1.0.0"
SOURCE_LABEL = "DOH newsroom release"

MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
DATE = rf"(?:{MONTHS}) \d{{1,2}}, \d{{4}}"
NUM = r"(\d[\d,]*)"


class ReleaseParseError(ValueError):
    pass


def _text(raw: bytes) -> str:
    h = raw.decode("utf-8", "replace")
    h = re.sub(r"<script.*?</script>|<style.*?</style>", " ", h, flags=re.S)
    h = h.replace("\\r\\n", " ").replace('\\"', '"')
    t = htmlmod.unescape(re.sub(r"<[^>]+>", " ", h))
    t = re.sub(r"<[^>]+>", " ", t)  # tags that were escaped inside embedded page data
    return re.sub(r"\s+", " ", t)


def _d(s: str) -> date:
    return datetime.strptime(s.replace("  ", " "), "%B %d, %Y").date()


def _n(s: str | None) -> int | None:
    return int(s.replace(",", "")) if s else None


def _find(pattern: str, text: str) -> re.Match[str] | None:
    return re.search(pattern, text, re.I)


def parse(raw: bytes) -> dict[str, Any]:
    text = _text(raw)
    m = _find(rf"({DATE})\s+[A-Z][a-z]+(?: [A-Z][a-z]+)?, PA\b", text) or _find(
        rf"({DATE})\s+Governor\b", text
    )
    if m is None:
        raise ReleaseParseError("release dateline not found")
    as_of = _d(m.group(1))
    body = text[m.end() :]

    row: dict[str, Any] = {}
    block = {
        "new_since": rf"New Positive Cases \(since ({DATE})\) ?:? ?{NUM}",
        "counties": rf"Total Counties ?:? ?{NUM}",
        "cum": rf"Total Cumulative Cases ?:? ?{NUM}",
        "hosp": rf"Total Hospitalizations ?:? ?{NUM}",
        "deaths": rf"Total (?:Cumulative |Confirmed )?Measles-Associated Deaths ?:? ?{NUM}",
        "vacc": rf"Measles cases among vaccinated individuals ?:? ?{NUM}",
    }
    got = {k: _find(p, body) for k, p in block.items()}
    headline = (
        _find(rf"{NUM} measles cases have been confirmed across {NUM} counties", body)
        or _find(rf"{NUM} cases of measles across {NUM} counties", body)
        or _find(rf"{NUM} cases in {NUM} counties", body)
    )
    if got["cum"]:
        row["cum_cases"] = _n(got["cum"].group(1))
    elif headline:
        row["cum_cases"] = _n(headline.group(1))
    else:
        alt = _find(rf"In 2026 so far, {NUM} measles cases", body) or _find(
            rf"residents with measles in 2026 to {NUM}", body
        )
        if alt is None:
            return {"as_of_date": as_of, "state": []}
        row["cum_cases"] = _n(alt.group(1))
    if got["counties"]:
        row["counties_with_cases"] = _n(got["counties"].group(1))
    elif headline:
        row["counties_with_cases"] = _n(headline.group(2))
    if got["new_since"]:
        row["new_since_date"] = _d(got["new_since"].group(1))
        row["new_since_count"] = _n(got["new_since"].group(2))
    for key, col in (
        ("hosp", "hospitalizations"),
        ("deaths", "deaths"),
        ("vacc", "vaccinated_cases"),
    ):
        hit = got[key]
        if hit is not None:
            row[col] = _n(hit.group(1))
    calendar = bool(
        _find(
            r"(so far in 2026|thus far in 2026|in 2026 so far|"
            r"with measles in 2026)",
            body,
        )
    )
    row.update(
        as_of_date=as_of,
        count_definition="calendar_year" if calendar else "unknown",
        date_precision="exact",
        is_backfill=True,
    )
    return {"as_of_date": as_of, "state": [row]}
