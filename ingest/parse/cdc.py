"""Parser for the CDC jurisdiction map data (sources S6): the CDC count for Pennsylvania.

The map file (``cdc_measles_cases_map``) has one row per geography and year with the same
``cases_2026`` on each, but no date. The date comes from the CDC cases page
(``cdc_measles_national``) captured at or before the map: "As of <date>, N confirmed measles
cases ... Among these, M measles cases were reported by K jurisdictions". The page date is
used only when the map's 2026 total over all jurisdictions equals M and its count of
jurisdictions with cases equals K, so both describe the same snapshot (I6). Otherwise no row
is stored and a ``DATE_TO_CONFIRM`` flag is raised.

CDC counts are a cross-check (S6): DOH stays primary, and CDC rows never join the DOH series.
"""

from __future__ import annotations

import html as htmlmod
import json
import re
from datetime import date, datetime
from typing import Any

PARSER_VERSION = "1.0.0"
SOURCE_LABEL = "CDC measles cases by jurisdiction"
STATE = "Pennsylvania"

_AS_OF = re.compile(r"As of ([A-Z][a-z]+ \d{1,2}, \d{4}), ([\d,]+) confirmed")
_JURIS = re.compile(r"Among these, ([\d,]+) measles cases were reported by (\d+) jurisdictions")


class CdcParseError(ValueError):
    pass


def _int(v: Any) -> int:
    return int(str(v).replace(",", "").strip())


def page_snapshot(page: bytes) -> dict[str, Any] | None:
    """Date and totals stated in the CDC cases page text, or None if not found."""
    t = page.decode("utf-8", "replace")
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"\s+", " ", htmlmod.unescape(re.sub(r"<[^>]+>", " ", t)))
    a, j = _AS_OF.search(t), _JURIS.search(t)
    if a is None or j is None:
        return None
    return {
        "as_of_date": datetime.strptime(a.group(1), "%B %d, %Y").date(),
        "us_total": _int(a.group(2)),
        "jurisdiction_total": _int(j.group(1)),
        "jurisdictions": int(j.group(2)),
    }


def parse(map_bytes: bytes, page: dict[str, Any] | None) -> dict[str, Any]:
    """Return ``{"state": [rows], "flags": [(code, text)]}`` for Pennsylvania."""
    rows = json.loads(map_bytes)
    if not isinstance(rows, list) or not rows:
        raise CdcParseError("map data is not a non-empty list")
    by_geo: dict[str, int] = {}
    for r in rows:
        if not isinstance(r, dict) or "geography" not in r or "cases_2026" not in r:
            raise CdcParseError(f"unexpected map row {r!r}"[:200])
        v = _int(r["cases_2026"])
        if by_geo.setdefault(r["geography"], v) != v:
            raise CdcParseError(f"conflicting cases_2026 for {r['geography']}")
    if STATE not in by_geo:
        raise CdcParseError(f"{STATE} not in the map data")
    total, nonzero = sum(by_geo.values()), sum(1 for v in by_geo.values() if v > 0)
    if page is None:
        return {
            "state": [],
            "flags": [("DATE_TO_CONFIRM", "CDC map has no date and no CDC page text was found")],
        }
    if (total, nonzero) != (page["jurisdiction_total"], page["jurisdictions"]):
        return {
            "state": [],
            "flags": [
                (
                    "DATE_TO_CONFIRM",
                    f"CDC map totals {total} cases in {nonzero} jurisdictions, page as of "
                    f"{page['as_of_date']} says {page['jurisdiction_total']} in "
                    f"{page['jurisdictions']}: not the same snapshot, date unknown",
                )
            ],
        }
    as_of: date = page["as_of_date"]
    return {
        "state": [
            {
                "as_of_date": as_of,
                "cum_cases": by_geo[STATE],
                "count_definition": "calendar_year",
                "date_precision": "exact",
                "is_backfill": False,
                "notes": (
                    f"CDC cross-check: cases reported to CDC; dated from the CDC page "
                    f"(US {page['us_total']}, {page['jurisdiction_total']} in "
                    f"{page['jurisdictions']} jurisdictions, matching the map)"
                ),
            }
        ],
        "flags": [],
    }
