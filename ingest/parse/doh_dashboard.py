"""Parser for the DOH dashboard capture, access path A (G1, docs/probe_report.md).

Input: the ``responses`` artefact of one capture (report data API responses, each tagged
with the view it was captured under). Output rows for ``case_state``, ``case_county``,
``vaccine_doses`` and ``case_demographics``.

- ``as_of_date`` is the report's "Last Updated" measure (``meas_dlm``), not the fetch date.
- The count definition of each headline figure comes from the query's own TimeFrame filter:
  "Year to date" is ``calendar_year`` and "April - Present" is ``since_april``. "January -
  March" is not stored as its own definition (E14 allows only the two plus ``unknown``).
- County counts come from the "Cases by County" table, which lists counties with cases; the
  county map lists all counties, so a county on the map but not in the table is a reported
  zero. The county table has no TimeFrame filter: it is labelled ``calendar_year`` only when
  its total equals the year-to-date total of the same capture, else ``unknown`` with a flag.
- Vaccine doses come from the "Measles Vaccine Administered" page: MMR doses given by DOH
  staff, statewide, by month of 2026 (the page says "Month (2026)"; the year is taken from
  the report's own table name, not from ``as_of_date``). The month containing ``as_of_date``
  is partial (``period_complete`` false). The report gives no dose number, so first, second
  and early infant doses cannot be told apart. Anything unexpected in the dose chart raises a
  flag and stores no dose rows; it never stops the case tables from being parsed.
- ``case_demographics`` (statewide, "Year to date" so ``calendar_year``): cases by age group
  and by month of report date ("Cases by Age and Time"), and hospitalized cases with their
  denominators by age band ("Hospitalizations", cards such as "198 of 1,004"). A blank cell
  in the report is stored as null, not zero (I5). Each set must add up to the year-to-date
  total of the same capture; if a set does not, or looks different, it is flagged and not
  stored.
"""

from __future__ import annotations

import calendar
import re
from datetime import UTC, date, datetime
from typing import Any

from ingest.parse.dsr import decode_result, where_values
from ingest.reference import crosswalk, pa_counties

PARSER_VERSION = "1.2.0"  # 1.1.0: MMR doses by DOH staff; 1.2.0: age, month, hospitalization
SOURCE_LABEL = "DOH measles dashboard"

T = "PAmeasles2026_Public"
M = "PAmeasles2026_map_Publicv2"
CARD = {
    f"Sum({T}.count)": "cum_cases",
    f"Sum({T}.newcase)": "new_7day",
    f"Sum({T}.hosp)": "hospitalizations",
    f"Sum({T}.deaths)": "deaths",
}
NOTE_CARDS = {
    f"{T}.Percentage Fully Vaccinated2": "fully vaccinated",
    f"{T}.Percentage Under18": "under 18",
}
DEFINITION = {"Year to date": "calendar_year", "April - Present": "since_april"}
LAST_UPDATED = f"Min({T}.meas_dlm)"
COUNTY = f"{M}.County"
COUNTY_COUNT = f"Sum({M}.COUNT)"
COUNTIES_WITH_CASES = f"Min({M}.County)"  # the report's own card: number of counties
V = "PAmeasles2026_Public_mmr"
REPORT_YEAR = 2026  # the year in the report's table names and chart axes, "Month (2026)"
DOSE_MONTH = f"{V}.vaccination_date.Variation.Date Hierarchy.Month"
DOSE_COUNT = f"CountNonNull({V}.vaccination_code)"
MONTHS = {m: i for i, m in enumerate(calendar.month_name) if m}
AGE = ("AgeDimTable.agegrp", f"CountNonNull({T}.agegrp)")
REPORT_MONTH = (f"{T}.reportdate.Variation.Date Hierarchy.Month", f"Sum({T}.count)")
AGE_GROUPS = ("0-4", "5-9", "10-17", "18-24", "25-49", "50-64", "65+", "Unk")
HOSP_CARDS = {
    f"Min({T}.hosptotal)": "all",
    f"Min({T}.hospunder18)": "under18",
    f"Min({T}.hosp18plus)": "18plus",
}
X_OF_Y = re.compile(r"^\s*([\d,]+)\s+of\s+([\d,]+)\s*$")


class DashboardParseError(ValueError):
    pass


def _queries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for r in bundle.get("responses", []):
        if "querydata" not in r["url"]:
            continue
        res = decode_result(r["body"])
        names = [s["Name"] for s in res["select"]]
        out.append(
            {
                "view": r.get("view"),
                "names": names,
                "blocks": res["blocks"],
                "timeframe": where_values(r.get("post_data"), "TimeFrame"),
            }
        )
    return out


def _single(q: dict[str, Any]) -> Any:
    rows = q["blocks"].get("DM0", [])
    if len(rows) != 1:
        raise DashboardParseError(f"expected one value for {q['names']}, got {len(rows)} rows")
    return rows[0][q["names"][0]]


def _agree(store: dict[Any, Any], key: Any, value: Any) -> None:
    if key in store and store[key] != value:
        raise DashboardParseError(f"conflicting values for {key}: {store[key]} vs {value}")
    store[key] = value


def _as_of(queries: list[dict[str, Any]]) -> date:
    stamps: dict[str, Any] = {}
    for q in queries:
        if q["names"] == [LAST_UPDATED]:
            _agree(stamps, "dlm", _single(q))
    if "dlm" not in stamps:
        raise DashboardParseError("no Last Updated value in the capture")
    return datetime.fromtimestamp(int(stamps["dlm"]) / 1000, UTC).date()


def parse(bundle: dict[str, Any]) -> dict[str, Any]:
    """Return ``{"as_of_date", "state": [rows], "county": [rows], "flags": [(code, text)]}``.
    Rows hold table-specific columns only; the runner adds provenance columns."""
    queries = _queries(bundle)
    if not queries:
        raise DashboardParseError("no data query responses in the capture")
    as_of = _as_of(queries)
    flags: list[tuple[str, str]] = []

    cards: dict[tuple[str, str], Any] = {}
    for q in queries:
        if len(q["names"]) == 1 and len(q["timeframe"]) == 1:
            name, tf = q["names"][0], q["timeframe"][0]
            if name in CARD or name in NOTE_CARDS:
                _agree(cards, (tf, name), _single(q))

    table: dict[str, int] = {}
    table_total: int | None = None
    map_counties: set[str] = set()
    community: set[str] | None = None
    counties_with_cases: int | None = None
    for q in queries:
        if q["names"] == [COUNTY, COUNTY_COUNT]:
            for trow in q["blocks"].get("DM1", []):
                _agree(table, trow[COUNTY], int(trow[COUNTY_COUNT]))
            for trow in q["blocks"].get("DM0", []):
                if "A0" in trow:
                    table_total = int(trow["A0"])
        elif q["names"] and q["names"][0] == COUNTY and "RangeDimTablev3.countrange" in q["names"]:
            map_counties |= {r[COUNTY] for r in q["blocks"].get("DM0", []) if r.get(COUNTY)}
        elif q["names"] == [COUNTY] and q["view"] == "community_transmission":
            community = {r[COUNTY] for r in q["blocks"].get("DM0", []) if r.get(COUNTY)}
        elif q["names"] == [COUNTIES_WITH_CASES] and q["view"] == "county":
            counties_with_cases = int(_single(q))

    state: list[dict[str, Any]] = []
    ytd_total = cards.get(("Year to date", f"Sum({T}.count)"))
    for tf, definition in DEFINITION.items():
        if (tf, f"Sum({T}.count)") not in cards:
            continue
        row: dict[str, Any] = {
            "as_of_date": as_of,
            "count_definition": definition,
            "date_precision": "exact",
            "is_backfill": False,
        }
        for name, col in CARD.items():
            v = cards.get((tf, name))
            row[col] = int(v) if v is not None else None
        notes = []
        for name, label in NOTE_CARDS.items():
            v = cards.get((tf, name))
            if v is not None:
                try:
                    notes.append(f"{label} {float(v):.1%}")
                except ValueError:
                    notes.append(f"{label} {v}")
        row["notes"] = "; ".join(notes) or None
        state.append(row)

    county_rows: list[dict[str, Any]] = []
    if table:
        if table_total is not None and sum(table.values()) != table_total:
            flags.append(
                (
                    "COUNTY_SUM_MISMATCH",
                    f"county table rows sum to {sum(table.values())}, table total {table_total}",
                )
            )
        total = table_total if table_total is not None else sum(table.values())
        if ytd_total is not None and total == int(ytd_total):
            definition = "calendar_year"
            for r in state:
                if r["count_definition"] == "calendar_year":
                    r["counties_with_cases"] = counties_with_cases
        else:
            definition = "unknown"
            flags.append(
                (
                    "DEFINITION_UNKNOWN",
                    f"county table total {total} differs from the year-to-date total {ytd_total}",
                )
            )
        xw = crosswalk.build(pa_counties.COUNTIES)
        names = map_counties | set(table)
        for name in sorted(names):
            fips = crosswalk.resolve(name, xw)
            county_rows.append(
                {
                    "as_of_date": as_of,
                    "county_fips": fips,
                    "cum_cases": table.get(name, 0),
                    "count_definition": definition,
                    "date_precision": "exact",
                    "is_backfill": False,
                    "community_transmission": (name in community)
                    if community is not None
                    else None,
                }
            )
    else:
        flags.append(("PARSE_SCHEMA_CHANGE", "county table not found in the capture"))
    doses, dose_flags = _doses(queries, as_of)
    flags += dose_flags
    demo, demo_flags = _demographics(queries, as_of, ytd_total)
    flags += demo_flags
    return {
        "as_of_date": as_of,
        "state": state,
        "county": county_rows,
        "doses": doses,
        "demographics": demo,
        "flags": flags,
    }


def _demo_row(as_of: date, dimension: str, category: str, cases: int | None) -> dict[str, Any]:
    return {
        "as_of_date": as_of,
        "dimension": dimension,
        "category": category,
        "cases": cases,
        "county_fips": None,
        "count_definition": "calendar_year",
    }


def _demographics(
    queries: list[dict[str, Any]], as_of: date, ytd: Any
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    rows: list[dict[str, Any]] = []
    flags: list[tuple[str, str]] = []
    total = int(ytd) if ytd is not None else None

    def bad(what: str) -> None:
        flags.append(("DEMOGRAPHIC_SUM_MISMATCH", f"{what} not stored"))

    def series(names: tuple[str, str]) -> list[dict[str, Any]] | None:
        found = [
            q
            for q in queries
            if tuple(q["names"]) == names and q["timeframe"] in ([], ["Year to date"])
        ]
        if not found:
            return None
        first = found[0]["blocks"].get("DM0", [])
        if any(q["blocks"].get("DM0", []) != first for q in found[1:]):
            return []  # two views disagree: treated as a problem below
        return first

    age = series(AGE)
    if age is None:
        flags.append(("PARSE_SCHEMA_CHANGE", "cases by age group not found in the capture"))
    else:
        got: dict[Any, Any] = {r.get(AGE[0]): r.get(AGE[1]) for r in age}
        n = sum(int(v) for v in got.values() if v is not None)
        if set(got) != set(AGE_GROUPS) or total is None or n != total:
            bad(f"cases by age group (groups {sorted(map(str, got))}, sum {n}, total {total})")
        else:
            rows += [
                _demo_row(as_of, "age_group", g, None if got[g] is None else int(got[g]))
                for g in AGE_GROUPS
            ]

    months = series(REPORT_MONTH)
    if months is None:
        flags.append(("PARSE_SCHEMA_CHANGE", "cases by report month not found in the capture"))
    else:
        got = {r.get(REPORT_MONTH[0]): r.get(REPORT_MONTH[1]) for r in months}
        if not all(isinstance(m, str) for m in got):
            got = {"?": None}  # an unexpected key fails the month check below
        n = sum(int(v) for v in got.values() if v is not None)
        late = [
            m
            for m, v in got.items()
            if m in MONTHS and v is not None and date(REPORT_YEAR, MONTHS[m], 1) > as_of
        ]
        if not set(got) <= set(MONTHS) or late or total is None or n != total:
            bad(f"cases by report month (sum {n}, total {total}, after as-of {late})")
        else:
            rows += [
                _demo_row(
                    as_of,
                    "report_month",
                    f"{REPORT_YEAR}-{MONTHS[m]:02d}",
                    None if got[m] is None else int(got[m]),
                )
                for m in sorted(got, key=lambda m: MONTHS[m])
                if date(REPORT_YEAR, MONTHS[m], 1) <= as_of
            ]

    cards: dict[str, tuple[int, int]] = {}
    for q in queries:
        if q["names"] and q["names"][0] in HOSP_CARDS and q["timeframe"] == ["Year to date"]:
            m = X_OF_Y.match(str(_single(q)))
            band = HOSP_CARDS[q["names"][0]]
            if m is None:
                cards[band] = (-1, -1)
                continue
            val = (int(m.group(1).replace(",", "")), int(m.group(2).replace(",", "")))
            if cards.get(band, val) != val:
                cards[band] = (-1, -1)
            else:
                cards[band] = val
    if not cards:
        flags.append(("PARSE_SCHEMA_CHANGE", "hospitalization cards not found in the capture"))
    elif (
        set(cards) != set(HOSP_CARDS.values())
        or any(h < 0 or h > c for h, c in cards.values())
        or cards["all"][1] != total
        or cards["under18"][0] + cards["18plus"][0] > cards["all"][0]
        or cards["under18"][1] + cards["18plus"][1] > cards["all"][1]
    ):
        bad(f"hospitalizations by age band ({cards}, total {total})")
    else:
        for band in ("under18", "18plus", "all"):
            rows.append(_demo_row(as_of, "age_band", band, cards[band][1]))
            rows.append(_demo_row(as_of, "hospitalized_age_band", band, cards[band][0]))
    return rows, flags


def _doses(
    queries: list[dict[str, Any]], as_of: date
) -> tuple[list[dict[str, Any]], list[tuple[str, str]]]:
    months: dict[int, int] = {}
    seen = False
    problem: str | None = None
    for q in queries:
        if q["names"] != [DOSE_MONTH, DOSE_COUNT]:
            continue
        seen = True
        for r in q["blocks"].get("DM0", []):
            name, n = r.get(DOSE_MONTH), r.get(DOSE_COUNT)
            if name not in MONTHS:
                problem = f"unexpected month {name!r} in the vaccine doses chart"
            elif n is None:
                # The chart's axis lists all twelve months; later months have no value.
                if date(REPORT_YEAR, MONTHS[name], 1) <= as_of:
                    problem = f"no dose count for {name} {REPORT_YEAR} (as of {as_of})"
            elif date(REPORT_YEAR, MONTHS[name], 1) > as_of:
                problem = f"doses reported for {name} {REPORT_YEAR}, after as-of date {as_of}"
            elif months.get(MONTHS[name], int(n)) != int(n):
                problem = f"conflicting dose counts for {name}"
            else:
                months[MONTHS[name]] = int(n)
    if not seen:
        return [], [("PARSE_SCHEMA_CHANGE", "vaccine doses chart not found in the capture")]
    if problem:
        return [], [("PARSE_SCHEMA_CHANGE", f"vaccine doses not stored: {problem}")]
    rows = []
    for m in sorted(months):
        end = date(REPORT_YEAR, m, calendar.monthrange(REPORT_YEAR, m)[1])
        rows.append(
            {
                "as_of_date": as_of,
                "period_start": date(REPORT_YEAR, m, 1),
                "period_end": end,
                "period_complete": end < as_of,
                "doses": months[m],
                "administered_by": "doh_staff",
                "geography": "state",
            }
        )
    return rows, []
