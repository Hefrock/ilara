"""Parser for the DOH school immunization county summary (``.xls``, sources S2, U3).

Layout (2025-2026 file, recorded in docs/schemas.md): a "Document map" sheet, then one sheet
per county. Each county sheet has "School Year: YYYY - YYYY", "County: NN - Name", a header
row starting with "Grade", and for each grade a "<Grade> - Total" row of counts followed by
a "Percentage:" row. Percentages are recomputed from the counts (count / enrolled x 100) so the
stored value has a stated denominator. An empty cell stays null, never 0.
"""

from __future__ import annotations

import re
from typing import Any

import xlrd

from ingest.reference import crosswalk, pa_counties

PARSER_VERSION = "1.0.1"  # 1.0.1: rows carry this source's own label
SOURCE_LABEL = "DOH school immunization survey summary by county"

GRADES = {"kindergarten": "kindergarten", "7th grade": "grade_7", "12th grade": "grade_12"}
COLUMNS = {  # output column -> words that must all appear in the header cell
    "enrolled": ("total", "enrolled"),
    "mmr": ("mmr",),
    "med": ("medical", "exempt"),
    "relig": ("religious", "exempt"),
    "philos": ("philos",),
    "provisional": ("provisional",),
}


class SchoolParseError(ValueError):
    pass


def _norm(v: Any) -> str:
    return re.sub(r"[\s-]+", " ", str(v)).strip().lower()


def _num(v: Any) -> float | None:
    if v in ("", None):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _pct(n: float | None, d: float | None) -> float | None:
    if n is None or not d:
        return None
    return round(100.0 * n / d, 4)


def parse(data: bytes) -> list[dict[str, Any]]:
    wb = xlrd.open_workbook(file_contents=data)
    xw = crosswalk.build(pa_counties.COUNTIES)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for sh in wb.sheets():
        cells = [[sh.cell_value(r, c) for c in range(sh.ncols)] for r in range(sh.nrows)]
        flat = [str(v) for row in cells for v in row]
        county_cell = next((v for v in flat if v.startswith("County:")), None)
        if county_cell is None:
            continue  # the document map
        year_cell = next((v for v in flat if v.startswith("School Year:")), None)
        if year_cell is None:
            raise SchoolParseError(f"sheet {sh.name}: no school year")
        y = re.findall(r"\d{4}", year_cell)
        school_year = f"{y[0]}-{y[1]}"
        name = county_cell.split("-", 1)[1].strip()
        fips = crosswalk.resolve(name, xw)
        if fips in seen:
            raise SchoolParseError(f"county {name} appears twice")
        seen.add(fips)
        header_i = next((i for i, row in enumerate(cells) if _norm(row[0]) == "grade"), None)
        if header_i is None:
            raise SchoolParseError(f"sheet {sh.name}: no Grade header row")
        header = [_norm(v) for v in cells[header_i]]
        col: dict[str, int] = {}
        for key, words in COLUMNS.items():
            idx = [i for i, h in enumerate(header) if all(w in h for w in words)]
            if len(idx) != 1:
                raise SchoolParseError(f"sheet {sh.name}: column {key} matched {idx}")
            col[key] = idx[0]
        for row in cells[header_i + 1 :]:
            label = _norm(row[0])
            if not label.endswith("total"):
                continue
            grade = next((g for k, g in GRADES.items() if label.startswith(k)), None)
            if grade is None:
                continue
            enrolled = _num(row[col["enrolled"]])
            rows.append(
                {
                    "school_year": school_year,
                    "county_fips": fips,
                    "grade": grade,
                    "enrolled": int(enrolled) if enrolled is not None else None,
                    "mmr_up_to_date_pct": _pct(_num(row[col["mmr"]]), enrolled),
                    "med_exempt_pct": _pct(_num(row[col["med"]]), enrolled),
                    "relig_exempt_pct": _pct(_num(row[col["relig"]]), enrolled),
                    "philos_exempt_pct": _pct(_num(row[col["philos"]]), enrolled),
                    "provisional_pct": _pct(_num(row[col["provisional"]]), enrolled),
                }
            )
    if len(seen) != len(pa_counties.COUNTIES):
        raise SchoolParseError(f"expected 67 county sheets, found {len(seen)}")
    return rows


# ---------------------------------------------------------------- school level (U4)

SCHOOL_SOURCE_LABEL = "DOH school immunization rates by school"
SCHOOL_GRADES = {"Kindergarten": "kindergarten", "7th Grade": "grade_7", "12th Grade": "grade_12"}
SCHOOL_COLUMNS = [
    "County",
    "School",
    "Grade",
    "Total Students Enrolled",
    "MMR Percent",
    "Medical Exemption Percent",
    "Religious Exemption Percent",
    "Philosophical Exemption Percent",
]


def _widget_table(html: str) -> tuple[list[str], list[list[Any]]]:
    import json

    m = re.search(r'<script type="application/json" data-for="[^"]+">(.*?)</script>', html, re.S)
    if m is None:
        raise SchoolParseError("no embedded table widget found")
    x = json.loads(m.group(1))["x"]
    header = re.findall(r"<th>(.*?)</th>", x["container"])
    cols = x["data"]
    if len(header) != len(cols):
        raise SchoolParseError(f"{len(header)} headers but {len(cols)} data columns")
    n = len(cols[0])
    return header, [[c[i] for c in cols] for i in range(n)]


def parse_school(data: bytes) -> list[dict[str, Any]]:
    """The by-school page embeds its table as an htmlwidgets DataTable (column-major JSON).
    Rates are fractions; a school-grade with fewer than 20 students has every rate null,
    shown as "ND" on the page: those rows get ``suppressed_flag`` true and null rates, never 0.
    """
    import json

    html = data.decode("utf-8", "replace")
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    years = re.findall(r"(20\d\d)\s*[-–]\s*(20\d\d)", title.group(1) if title else "")
    if not years:
        raise SchoolParseError("school year not found in the page title")
    school_year = f"{years[0][0]}-{years[0][1]}"
    header, table = _widget_table(html)
    missing = [c for c in SCHOOL_COLUMNS if c not in header]
    if missing:
        raise SchoolParseError(f"columns missing: {missing}")
    ix = {c: header.index(c) for c in SCHOOL_COLUMNS}
    xw = crosswalk.build(pa_counties.COUNTIES)
    out: list[dict[str, Any]] = []
    for r in table:
        grade = SCHOOL_GRADES.get(r[ix["Grade"]])
        if grade is None:
            raise SchoolParseError(f"unknown grade {r[ix['Grade']]!r}")
        rates = [r[i] for i in range(ix["Total Students Enrolled"] + 1, len(header))]
        suppressed = all(v is None for v in rates)

        def pct(col: str, row: list[Any] = r) -> float | None:
            v = row[ix[col]]
            return None if v is None else round(100.0 * float(v), 4)

        exempt = {
            "medical": pct("Medical Exemption Percent"),
            "religious": pct("Religious Exemption Percent"),
            "philosophical": pct("Philosophical Exemption Percent"),
        }
        out.append(
            {
                "school_year": school_year,
                "school_name": r[ix["School"]],
                "county_fips": crosswalk.resolve(r[ix["County"]], xw),
                "grade": grade,
                "enrolled": int(r[ix["Total Students Enrolled"]]),
                "mmr_pct": pct("MMR Percent"),
                "exempt_pcts": None if suppressed else json.dumps(exempt, sort_keys=True),
                "suppressed_flag": suppressed,
            }
        )
    return out
