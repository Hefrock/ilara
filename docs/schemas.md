# Source file layouts

Observed layouts of captured source files (sources register U3, U4). Each entry cites the raw
file it was read from. Parsers fail loudly when a layout changes (`PARSE_SCHEMA_CHANGE`).

## DOH school immunization summary by county (`doh_school_imm_county`, U3)

Observed in `data/raw/doh_school_imm_county/2026/20261007T111620Z_9a7406dfecb0.xls`
(2025-2026, `.xls`, read with `xlrd`).

- Sheet 1 "Document map": index of the 67 county sheets ("01 - Adams" ... "67 - York").
- Sheets 2 to 68: one county each. Cells of note:
  - "School Year: 2025 - 2026" (row 3)
  - "County: NN - Name" (column A, row 6 or 7)
  - header row starting "Grade". Columns: Total Students Enrolled; DTaP/DTP/DT 4 doses; Polio
    4 doses; MMR 2 doses or more; HEPB 3 doses; Varicella had disease; Varicella 2 doses;
    Tdap/Td 1 dose; MCV 1 dose; MCV (16+) 1 dose; MCV 2 doses; Number Medical Exempt; Number
    Religious Exempt; Number Philosophical Exempt; Number Provisionally Enrolled; Number Denied
    Admission; Number Non-Compliant.
  - rows "Kindergarten - Total", "7th Grade - Total", "12th Grade - Total" hold counts, each
    followed by a "Percentage:" row (fraction of enrolled).
  - "Number of schools reporting" row.
- The parser stores counts as percentages of enrolled (0 to 100) with the enrolled count, and
  checks against the published percentage rows only implicitly through T3.13.

## DOH school immunization by school (`doh_school_imm_school`, U4)

Observed in `data/raw/doh_school_imm_school/2026/20261007T111625Z_00162b993811.html.gz`.

- A Quarto page. The table is an htmlwidgets DataTable: `<script type="application/json"
  data-for="...">` holds `x.data`, a list of 20 columns (column-major), and `x.container`, the
  `<th>` header row: County, School, Grade, Total Students Enrolled, DTaP, Polio, MMR, Hep B,
  Varicella had disease, Varicella, Tdap, MCV4 1st dose, MCV4 16+ 1 dose, MCV4 2nd dose 16+,
  Medical, Religious and Philosophical Exemption, Enrolled Provisionally, Denied Admission,
  Noncompliant and Attending (all "Percent", as fractions).
- 5,943 rows (school x grade: Kindergarten, 7th Grade, 12th Grade), 67 counties, school names
  unique within county and grade. School year from the page title ("2025-2026").
- Rows with fewer than 20 enrolled have every rate null (displayed "ND"): 2,228 rows. The
  parser keeps them with `suppressed_flag = true` and null rates, never 0 (T3.14).

## DOH dashboard (`doh_dashboard`)

See `docs/probe_report.md` and `ingest/parse/doh_dashboard.py` (Power BI `querydata`
responses).

- `case_state`, `case_county`: headline cards and county counts (see the parser docstring).
- `case_state.source_refreshed_utc` (parser 1.3.0): when DOH last refreshed the report's data,
  from Power BI's own refresh metadata in the captured responses (ADR 0010); null when the
  capture carries none, and for rows from other sources.
- `vaccine_doses`: MMR doses administered by DOH staff, statewide, by month of 2026, from the
  "Measles Vaccine Administered" page (ADR 0004). The month containing `as_of_date` has
  `period_complete` false. No dose number is given.
- `case_demographics` (statewide, calendar year, parser 1.2.0): `age_group` (0-4, 5-9, 10-17,
  18-24, 25-49, 50-64, 65+, Unk), `report_month` (`YYYY-MM`, month of report date, the only
  dated case series the dashboard gives), `age_band` (cases under 18, 18 and over, all) and
  `hospitalized_age_band` (hospitalized cases in the same bands, from cards like "198 of
  1,004"). A blank cell is stored as null. Each set must add up to the year-to-date total of
  the same capture, else it is flagged `DEMOGRAPHIC_SUM_MISMATCH` and not stored.
  The report republished on 2026-10-13 has no `Unk` age group and no report-month chart
  (`report_month` ends with the 2026-10-09 capture). Parser 1.5.0 adds `onset_week`
  (category = the Monday that starts the onset week, `YYYY-MM-DD`) from the Epidemic Curve
  tab: weeks up to the as-of date only (later bars are placeholders); the current week is
  incomplete, and recent weeks are revised from capture to capture. Kept out of the model and
  the dashboard until reviewed (ADR 0014, 0015).

## DOH measles page (`doh_measles_page`)

No rows. The parser reads the page's Power BI dashboard links and raises
`DASHBOARD_LINK_CHANGED` when they differ from those on the page captured before, or when the
page shows none (ADR 0009). The registry URL of `doh_dashboard` follows the page's link.

## Capture log

Each record has `trigger`: the GitHub event that started the run (`schedule`,
`workflow_dispatch`) or `local`; records before 2026-10-15 have none. A dashboard capture that
did not reach the report (Power BI error from the data API, a placeholder page, or no report
tab opened) is `failed`, with `report unavailable: ...` in `error`; raw is still saved first.
`capture_log.is_good` applies the same test to older records, which logged such captures as
changed or unchanged; it decides capture-day cover, freshness, alerts and releases.

## CDC jurisdiction map (`cdc_measles_cases_map`, S6)

`case_state` rows for Pennsylvania (`source_id` `cdc_measles_cases_map`, T1, `calendar_year`).
The map file has no date; the row takes the "As of" date of the CDC cases page captured at or
before it, and only when the map's 2026 total and number of jurisdictions with cases equal the
page's. Otherwise nothing is stored and `DATE_TO_CONFIRM` is raised. These rows are listed in
`ingest.access.CROSSCHECK_SOURCES`: they never join the DOH statewide series, its monotonicity
check or the same-date reconciliation, and the dashboard compares them with the nearest DOH
totals instead.
