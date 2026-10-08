# SOURCES: facts about the world (inputs, parameters, known data issues)

Purpose: the verified and unverified facts the build depends on. This file records what is true about the sources, not what to build (see HANDOFF.md) and not how to behave (see CLAUDE.md). Copy to `docs/sources.md` and keep it current as items are verified.

Status labels: VERIFIED (seen in a fetched page or search result), PARTIAL, UNVERIFIED (general knowledge or inference). Every UNVERIFIED item has a register ID in the table at the end and a work package that resolves it.

Lines that say what to do with a fact are interpretation notes; the binding rules are in CLAUDE.md and the tasks are in HANDOFF.md.

Source tiers: T1 official primary; T2 peer-reviewed or MMWR; T3 news or Wikipedia; T3-derived news-attributed DOH figures (CLAUDE.md I4).

## S1. PA DOH measles dashboard (primary case data)

- Entry page (VERIFIED): https://www.pa.gov/agencies/health/diseases-conditions/infectious-disease/measles (short link pa.gov/measles).
- Dashboard is an embedded Microsoft Power BI Gov report (VERIFIED): https://app.powerbigov.us/view?r=eyJrIjoiOGVkYzBiYjYtYTBhNy00MjVjLWFjZGQtM2Y3NDc4NmYxYzBiIiwidCI6IjQxOGUyODQxLTAxMjgtNGRkNS05YjZjLTQ3ZmM1YTlhMWJkZSJ9
- A static HTTP fetch returns only a loading spinner (VERIFIED). The content renders client-side, so a plain `requests` call will not work.
- Update schedule: Monday, Wednesday and Friday afternoons (VERIFIED, DOH launch release).
- Advertised contents (VERIFIED from DOH releases): cases per county, demographics including age, hospitalization rate, vaccination status of cases, counties with community transmission, deaths, vaccination efforts. Local news reporting adds these dashboard elements (T3, VERIFIED): a rolling seven-day new-case figure (106 in the week to Oct 5, down from 114 the week before), the share of cases under 18 (32 percent, up from 31), and a list of counties with community transmission that DOH updates each Monday (12 counties as of Oct 5: Centre, Chester, Clarion, Clearfield, Indiana, Jefferson, Lancaster, Mifflin, Snyder, Somerset, Union, York). Exact field names, whether a time series is exposed, and whether export is enabled are still UNVERIFIED.
- Reporting artifacts to model, not clean away (T3, VERIFIED): the dashboard added 55 cases between a Wednesday and Friday update but only 13 between Friday and Monday, so day-of-week patterns exist. Counts are not daily incidence.
- Access path: the report is client-rendered; whether its JSON query responses can be captured, and whether that is permitted, is UNVERIFIED (register U1, U2, U22; resolved by WP2 probe). Fallbacks are defined in HANDOFF.md WP2.
- Statewide dated series: T1 rows are in `data/seed/statewide_backfill.csv`; news-derived and secondary rows are in `data/sensitivity/seed/statewide_t3_derived.csv` (every row has tier, definition and a source label). Each DOH release carries a stats block (new cases since date, total counties, cumulative cases, hospitalizations, deaths, vaccinated cases); fetch each release page for its publication date. Dates marked `to_confirm` in the seed are unresolved and are WP3 backfill tasks.

- Implied-count facts: each release's "new since" figure implies an earlier cumulative count (about 460 on Aug 28, 497 on Aug 31, 624 on Sept 9, 903 on Sept 28). The test that checks these against the dated series is T3.5 in HANDOFF.md.
- Other markers (T3, UNVERIFIED against DOH): 12 cases January to March, none linked to the main outbreak; main outbreak began in late April in Lebanon County, 11 Lebanon residents diagnosed by May 6; 32 statewide by May 22; 84 by June 26 (72 in the Lancaster and Lebanon region); 114 by late July; about 393 around Aug 25 (Lancaster 185); about 767 around Sept 17 to 18 (150 hospitalized). A scientific paper citing CDC data put PA at 134 cases on July 23, which does not match the 114 late-July figure, so the July values need checking. Growth from late July to the 379 on Aug 21 is steep. It may be real (Mifflin went from 29 cases on Aug 25 to 118 on Oct 5 and Chester more than tripled since early August), but verify and flag it in the data quality report. Do not smooth it.
- Definition trap: some counts are calendar-year totals and some are "since April" outbreak-period counts. Record which one each value is.
- Dated county datapoints from local news quoting the dashboard are in `data/sensitivity/seed/county_t3_derived.csv` (tier `T3-derived`, see CLAUDE.md I4). The Oct 5 list is the first-snapshot sanity check for the dashboard parser.
- Age and pregnancy details (T3, optional covariates): 32 percent of cases under 18; more than 100 cases under age 4; more than a quarter of cases adults of childbearing age; 53 of 977 cases in pregnant women (DOH to the 19th, early Oct). The dashboard reportedly carries age, so check whether age bands are available by county.
- DOH death definition (VERIFIED): a death within 30 days of symptom onset with clinical evidence, a positive lab test, and no unrelated cause. This differs from CDC practice. The CDC national tally has at times excluded PA deaths. Treat deaths as an uncertain field.
- Wayback: the Internet Archive may hold captures of the pa.gov measles page and newsroom pages (CDX API technique UNVERIFIED, register U11; the dashboard itself will not archive because it is client-rendered).

## S2. School immunization data (susceptibility input, T1)

- County Excel summaries (VERIFIED links on https://www.pa.gov/agencies/health/programs/immunizations/rates). Note the extensions: `.xls` for 2023-2024 through 2025-2026 (needs `xlrd`), `.xlsx` for earlier.
  - 2025-2026: https://www.pa.gov/content/dam/copapwp-pagov/en/health/documents/topics/documents/programs/immunizations/School%20Immunization%20Survey%20Summary%20by%20County%202025-2026.xls
  - 2024-2025: same path, filename `School%20Immunization%20Survey%20Summary%20by%20County%202024-2025.xls`
  - 2023-2024: same path, filename `School%20Immunization%20Survey%20Summary%20by%20County%202023-2024.xls`
  - State summaries use the filename pattern `School%20Immunization%20Survey%20Summary%20for%20PA%202025-2026.xls`.
  - Sheet layout and column names are UNVERIFIED. Inspect before writing the parser and record the layout in `docs/schemas.md`.
- School-level interactive table, 2025-2026 (VERIFIED, published 2026-07-31): https://www.pa.gov/content/dam/copapwp-pagov/en/health/documents/topics/healthstatistics/school-immunizations/current/school-immunization-rates.html
  - A Quarto-generated HTML page. The fetch did not expose the table data; where the data are embedded (inline JSON or a data file) is UNVERIFIED (register U4).
  - Documented structure (VERIFIED): columns 1 to 4 are school name, county, total enrolled in the reported grades; columns 5 to 14 are percent up to date for DTaP, polio, MMR, Hep B, varicella (disease counts), and others including Tdap and MCV4; columns 15 to 17 are exemption percentages (medical, religious, philosophical); columns 18 to 20 are provisional enrolment, denied admission, and permitted to attend while not up to date.
  - Values display "ND" when enrolment is under 20 or the vaccine does not apply to the grade (VERIFIED). Schools with fewer than 20 students are therefore suppressed. Home-school students are folded into the school they would attend.
  - Covers more than 90 percent of schools (VERIFIED, DOH release). Grades covered: kindergarten, 7th, 12th. Self-reported each December through the School Immunization Law Report.
- Reference values (T3), usable as parser sanity checks: Lancaster County kindergarten MMR rate 87.6 percent (LancasterOnline); Chester County overall kindergarten MMR rate 94.5 percent (Inquirer); national kindergarten MMR 92.4 percent for 2025 to 2026 (ABC News citing CDC); school-level extremes reported in news, for example a Northumberland County school at 43.3 percent (WOLF). A reporter-compiled figure of 44 percent of 173 schools below 95 percent applies to a regional subset, not the state.
- Timing caveat: schools report in December, so the 2025-2026 data predate the outbreak by about four months and do not reflect the vaccination drive that followed (see S8). Treat school coverage as a baseline and model post-outbreak vaccination separately.
- Important limitation (inference, UNVERIFIED): the outbreak is concentrated in Amish and Mennonite communities in Lancaster, Lebanon and elsewhere. Small private or one-room schools may be suppressed or unreported, so the county school-based rate likely overstates immunity for the high-risk subpopulation. The model must treat this as an explicit uncertain parameter, not a footnote.

## S3. Population and age structure (T1)

- Census Vintage 2025 county totals and age and sex detail are published as file downloads at https://www.census.gov/programs-surveys/popest/data/data-sets.html (VERIFIED). The same page says current estimates are not supported by the Census API (VERIFIED), so download the files. Use "County Population Totals: 2020-2025" (March 2026) and "County Population by Characteristics: 2020-2025" (CC-EST2025-AGESEX, June 2026). Exact file URLs UNVERIFIED; navigate from the page.
- PA state open data portal has a Socrata dataset of county population estimates (VERIFIED existence): https://data.pa.gov/Census-Economic/Population-Estimates-Statewide-County-Current-Cens/hv5f-e4e3 . It appears to carry an older vintage (VERIFIED from the page description); do not use it for the 2025 vintage without checking.
- Statewide check value (VERIFIED, QuickFacts): Pennsylvania July 1, 2025 estimate 13,059,432. County populations must sum to this.

## S4. Mobility between counties (T1, dated)

- ACS 2016-2020 county-to-county commuting flows (VERIFIED existence): https://www.census.gov/data/tables/2020/demo/metro-micro/commuting-flows-2020.html . Also a cleaned bilateral version at https://www.nber.org/research/data/us-county-county-commuting-flows (VERIFIED existence).
- Do not confuse commuting flows with ACS migration flows (annual movers).
- Limitations: pre-2020s patterns, commuters only, and likely poor coverage of the high-risk community's movement. Use as a baseline gravity or flow prior, with a scenario that scales or replaces it.

## S5. Geometry

- Census cartographic boundary files, county layer, 1:500,000 state or national shapefile or geopackage (VERIFIED existence): https://www.census.gov/geographies/mapping-files/time-series/geo/cartographic-boundary.html . TIGER/Line 2025 shapefiles also exist (VERIFIED). Exact file names are UNVERIFIED; navigate from the page. In Python, `pygris` is a likely wrapper (UNVERIFIED).
- Filter to Pennsylvania (state FIPS 42). Pennsylvania county FIPS codes are believed to be the odd numbers 42001 to 42133 (UNVERIFIED, register U7). Codes to spot-check (UNVERIFIED): Lancaster 42071, Mifflin 42087, Chester 42029, Philadelphia 42101, Allegheny 42003. Expected county count: 67.
- County names differ in spelling and capitalization across Excel files, news lists and the dashboard; a crosswalk is required before any join (WP1).

## S6. CDC cross-check (T1)

- https://www.cdc.gov/measles/data-research/index.html . Reflects confirmed cases reported as of noon Thursday (VERIFIED). National total as of Oct 1, 2026 was 3,887 cases (VERIFIED). Use PA state counts from DOH as primary; use CDC only to cross-check and note divergence.
- The page text names Pennsylvania among the jurisdictions with cases but gives no state count (VERIFIED 2026-10-08 from capture `20261007T111650Z_e22bfc046224`, page updated October 2, 2026, data as of October 1). Its charts load configuration files (`data-config-url`): `/measles/states-cases-2024.json` (jurisdiction map) and `/measles/weekly-cases-chart.json` (weekly national chart). Both are captured daily (`cdc_measles_states_config`, `cdc_measles_weekly_config`) so the data files they point to can be added; the Pennsylvania count for the reconciliation table comes from there.

## S7. Parameter sources

| Parameter | Value | Status and source |
|---|---|---|
| Infectious window | 4 days before to 4 days after rash | VERIFIED, DOH measles page |
| Incubation | usually 7 to 14 days, up to 21 | VERIFIED, DOH measles page |
| MMR effectiveness | 93 percent one dose, 97 percent two doses | VERIFIED, ABC News citing CDC |
| Hospitalized fraction | nearly 20 percent | VERIFIED, DOH releases (note observed 198 of 1,004 is also about 20 percent) |
| Deaths | 1 to 3 per 1,000 cases expected; observed 5 of 1,004 | VERIFIED, DOH release; observed rate is higher, consistent with undercounting of mild cases |
| R0 | commonly cited 12 to 18 | UNVERIFIED, general knowledge; confirm from literature and treat as a prior |
| Latent period, generation time | about 10 to 12 days | UNVERIFIED, general knowledge; confirm |
| Outbreak size priors and calibration case | Texas 2025 | See literature below |

Literature to read before fixing priors (T2, VERIFIED existence):
- MMWR, Measles Update US Jan 1 to Apr 17 2025 (DOI 10.15585/mmwr.mm7414a1).
- MMWR Notes from the Field, West Texas response (https://www.cdc.gov/mmwr/volumes/75/wr/mm7523a2.htm); Texas outbreak ended Aug 18, 2025 with 762 cases, 99 hospitalizations, 2 deaths.
- EID October 2026, whole-genome sequencing of Texas measles virus (https://wwwnc.cdc.gov/eid/article/32/10/26-0494_article).
- Risk and Spatial Spread of a Measles Outbreak in Texas, county network transmission model parameterized with MMR coverage and mobility (PMC13307820; also on medRxiv). Closest published analogue to this project's design.
- Prior art on school-vaccination-based outbreak simulation exists (University of Colorado researcher quoted in news); search for it and cite rather than reinvent.

## S8. Health alerts, exposure notices and interventions (T1)

Why this matters: the model needs dated interventions and spatial-spread events, and no source above provides them.

- DOH Health Alert Network index (VERIFIED link): https://www.pa.gov/agencies/health/healthcare-and-public-health-professionals/han . 2026 alerts are listed in the seed events file (existence VERIFIED).
- Dated alerts, exposure notices and interventions are in `data/seed/events.csv` (T1) and `data/sensitivity/seed/events_t3.csv` (T3). Index of 2026 alerts and notices: HAN index above and the measles page media resources.
- Accounting rule (VERIFIED, HAN 838): the early infant dose is supplementary and does not count toward the routine two-dose series. An accelerated second dose does count (T3).

## S9. Local health departments (T1, cross-check and timing)

- PA has county and municipal health departments that publish separately from DOH (list page, VERIFIED link): https://www.pa.gov/agencies/health/about-us/county-municipal-health-depts .
- Lancaster County measles page with exposure sites (VERIFIED): https://www.lancastercountypa.gov/2983/Measles
- Philadelphia Department of Public Health alerts, archived at hip.phila.gov (VERIFIED); Delaware County Health Department and Chester County Health Department also issue measles information (Chester URL UNVERIFIED; locate it).
- Use these to cross-check DOH counts and to date local events. They may differ from state counts. Record differences, do not reconcile by hand.

## S10. Wastewater (optional validation covariate, T1)

- CDC NWSS "Wastewater Data for Measles" on data.cdc.gov (VERIFIED existence): https://data.cdc.gov/d/akvg-8vrb . The catalog showed it last updated 2026-09-22. Schema and API form are UNVERIFIED; data.cdc.gov datasets usually expose a Socrata JSON endpoint, so test `https://data.cdc.gov/resource/akvg-8vrb.json` and filter to Pennsylvania sites.
- WastewaterSCAN (Stanford) detected measles RNA in Delaware County on June 9 and 11. The Philadelphia-region case list on Oct 5 still showed zero cases in Delaware County (T3), a useful example of detection without confirmed cases.
- Limitations (VERIFIED): a July 2026 CDC report found wastewater testing missed an internationally circulating B3 genotype, and detections do not indicate how many people are infected. Use wastewater only as an early-warning covariate or a qualitative check, never as case counts.
- PA's own wastewater program (PaWSS) is linked in the DOH navigation (VERIFIED link); whether it publishes measles results is UNVERIFIED.

## S11. External importation context

- The model needs an external-introduction term and a boundary-effect note. Other outbreaks in 2025 to 2026 include South Carolina (997 cases by April 2026), Utah, Texas and Florida (T3). No cross-state mobility data were identified. Counties on the state border have unmodelled links to neighbouring states.
- Spatial pattern note (T3, VERIFIED): Chester County cases are concentrated along the Lancaster border, so geographic adjacency matters. Mifflin County is not adjacent to Lancaster, yet it is the second-largest cluster. A hypothesis, not a finding, is that social links between affiliated communities carry transmission beyond what commuting captures. The model should allow an adjacency term and a long-range term, and compare them.

## S12. Known data issues to surface, not hide

1. Same-county counts differ across articles at different dates (Mifflin 93, 94, 106, 118; statewide 903, 943, 1,004, and an undated early-October figure of 977 quoted with the pregnancy count, not seeded). Always key by as_of_date.
2. Reports are by report date, with lags to onset. Dashboard updates Monday, Wednesday and Friday only.
3. Probable cases may exist that are not counted as confirmed.
4. Death attribution is contested in at least one case (Lancaster coroner determination reported in news). CDC and DOH tallies differ.
5. School immunization data are self-reported, annual, and suppress small schools.
6. Commuting data are from 2016-2020.
7. Possible undercount in the outbreak community and an unusually high adult share of cases, noted by a researcher quoted in news (T3). Local physicians and health officials also believe the official count understates infections (T3).
8. Counts mix definitions: calendar-year versus since-April totals (S1). Record the definition per row.
9. Day-of-week reporting artifacts: 55 cases added between Wednesday and Friday versus 13 between Friday and Monday (T3). Do not treat dashboard deltas as daily incidence.
10. Numbers disagree across tiers: DOH versus CDC (a journal article citing CDC put PA at 134 on July 23, while a late-July figure of 114 appears elsewhere), and DOH versus CDC on deaths.
11. School vaccination data predate the outbreak (collected December 2025) and exclude small schools.
12. No cross-state mobility or importation data; border counties have unmodelled links.
13. Wastewater detections do not map to case counts and have known detection gaps (S10).
14. News and press releases give rounded or partial county lists. Keep the source name, URL and figure for every `T3-derived` row; never commit article text (CLAUDE.md I10).



## Verification register (every UNVERIFIED item, and where it is resolved)

| ID | Item | Resolved by | How it is closed |
|---|---|---|---|
| U1 | Dashboard JSON query responses capturable and permitted | WP2 probe | `docs/probe_report.md`, Gate G1 VERIFIED 2026-10-07: captured and parsed (docs/probe_report.md) |
| U2 | Dashboard field names, any history, any export | WP2 probe | `docs/probe_report.md` VERIFIED 2026-10-07: six visible pages and their fields listed in docs/probe_report.md; no export or history control seen |
| U3 | School county Excel sheet layouts | WP3 | `docs/schemas.md` plus golden parser tests VERIFIED 2026-10-07: layout of the 2025-2026 county file recorded in docs/schemas.md; parser golden test passes |
| U4 | Location of data in the school-level HTML | WP3 | `docs/schemas.md` VERIFIED 2026-10-07: embedded DataTable JSON in the page; layout in docs/schemas.md |
| U5 | Census population file URLs | WP1 | URLs recorded in `data/registry/source_registry.yml` PARTIAL 2026-10-07: totals and age-sex file URLs work (data/registry); commuting file URL still to find |
| U6 | Cartographic boundary file names; `pygris` usable | WP1 | registry entry plus T1.1 VERIFIED 2026-10-07: cb_2024_us_county_500k.zip captured; 67 valid PA counties (T1.1) |
| U7 | PA county FIPS pattern | WP1 | T1.1, T1.2 VERIFIED 2026-10-07: PA FIPS are 42001 to 42133 odd, matching the boundary and population files (T1.2) |
| U8 | CDC NWSS Socrata endpoint and schema | WP2 and WP3 (optional) | registry entry, schema doc |
| U9 | PA EDDIE exposes measles | Human (H9) | owner note in `docs/BLOCKERS.md` |
| U10 | PaWSS publishes measles | Human (H9) | owner note |
| U11 | Wayback CDX technique | WP3 backfill | pass or fail recorded in `docs/backfill_report.md` VERIFIED 2026-10-07: CDX query works (docs/backfill_report.md) |
| U12 | R0 prior 12 to 18 | WP6 | literature citation recorded in model config |
| U13 | Latent and generation time about 10 to 12 days | WP6 | literature citation recorded |
| U14 | HAN 822 PDF URL | WP3 backfill | `data/seed/events.csv` `url_status` set to `verified` |
| U15 | Chester County Health Department page | Human (H10) | registry entry |
| U16 | DOH release dates for 497 and 540; DOH release pages for 792 and 1,004 | WP3 backfill | `to_confirm` rows resolved; T3-derived rows corroborated VERIFIED 2026-10-07: 497 is the 2026-08-31 release, 540 the 2026-09-02 release (docs/backfill_report.md) |
| U17 | Count definition for 379 and later values | WP3 backfill | `count_definition` set, flag cleared PARTIAL 2026-10-07: from now on the dashboard states the definition (Year to date 1,004; April - Present 992; January - March 12, as of Oct 5); earlier seed values remain to confirm |
| U18 | `epydemix` maintained and suitable | WP6 | ADR |
| U19 | Amish and Mennonite coverage inference | WP6 | scenario parameter documented as assumption PARTIAL 2026-10-08: scenario parameter `under_covered` in `project/susceptibility/params.yml` (none, low, mid, high; same in every county, since no T1 source says where these communities live); the inference itself stays UNVERIFIED |
| U20 | Public PA measles sequences | Human (H9) | owner note |
| U21 | Scheduled-workflow disablement rules for public repos | Gate G5 | checked against current GitHub docs |
| U22 | GitHub-hosted runners can reach the dashboard | WP2 probe | `docs/probe_report.md` VERIFIED 2026-10-07: GitHub-hosted runners load the report (probe runs 37562037581, 37567917285) |
| U23 | GitHub Free private repositories lack branch protection; `GITHUB_TOKEN` pushes do not trigger workflows | WP0 | ADR, checked against current GitHub documentation |
