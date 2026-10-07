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

PARSER_VERSION = "1.0.0"
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
