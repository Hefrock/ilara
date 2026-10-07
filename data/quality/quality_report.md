# Data quality report

Generated 2026-10-07T11:31:13Z by `measles quality` (engine 1.0.0). Latest dashboard data as of 2026-10-05. Regenerated on every capture run; flags are the durable record (`data_quality_flag`).

Reported counts are a floor. Conflicts below are shown, not resolved (I5). Rows from the sensitivity store (news-derived, secondary) are labelled with their tier and are never used in default views.

## Open flags

- **DATE_TO_CONFIRM** (4)
  - curated: data/seed/statewide_backfill.csv sw-004: date to confirm
  - curated: data/seed/statewide_backfill.csv sw-005: date to confirm
  - sensitivity: data/sensitivity/seed/statewide_t3_derived.csv sw-m01: date to confirm
  - sensitivity: data/sensitivity/seed/statewide_t3_derived.csv sw-m04: date to confirm
- **PARSE_SCHEMA_CHANGE** (1)
  - curated: data/raw/doh_dashboard/2026/20261007T022732Z_f326ab94771c.json.gz: DashboardParseError: no data query responses in the capture
- **STALE_SNAPSHOT** (1)
  - curated: census_commuting: no good capture within 48 h (last good never)

## Capture freshness

- cdc_measles_national: last outcome changed, last good 2026-10-07T11:16:55Z (0 h ago)
- census_cartographic: last outcome changed, last good 2026-10-07T11:16:50Z (0 h ago)
- census_commuting: last outcome failed, last good never STALE
- census_popest_agesex: last outcome changed, last good 2026-10-07T11:16:40Z (0 h ago)
- census_popest_totals: last outcome changed, last good 2026-10-07T11:16:35Z (0 h ago)
- doh_dashboard: last outcome changed, last good 2026-10-07T03:43:11Z (8 h ago)
- doh_han_index: last outcome changed, last good 2026-10-07T11:16:20Z (0 h ago)
- doh_measles_page: last outcome changed, last good 2026-10-07T11:16:10Z (0 h ago)
- doh_newsroom: last outcome changed, last good 2026-10-07T11:16:15Z (0 h ago)
- doh_school_imm_county: last outcome changed, last good 2026-10-07T11:16:25Z (0 h ago)
- doh_school_imm_school: last outcome changed, last good 2026-10-07T11:16:30Z (0 h ago)
- local_hd_lancaster: last outcome changed, last good 2026-10-07T11:17:00Z (0 h ago)

## Implied counts

- sensitivity sw-008: 115 new with no start date; no implied count computed (see the weekly comparison below).
- curated sw-006: implies 624 on 2026-09-09 (676 - 52)
- curated sw-009: implies 903 on 2026-09-28 (943 - 40)
  - agrees with sensitivity seed_statewide:sw-008 (T3-derived) = 903 on 2026-09-28
- curated sw-004: implies 460 on 2026-08-28 (497 - 37) (row is quarantined: date to confirm)
- curated sw-005: implies 497 on 2026-08-31 (540 - 43) (row is quarantined: date to confirm)
  - hint: curated sw-004 (date to confirm) has the same count 497, so it may be as of 2026-08-31

## Seed conflicts

- sensitivity sw-008: 903 on 2026-09-28 with 115 new in the week implies 788 on 2026-09-21; sensitivity sw-007 (T3-derived) says 792: conflicts

## Non-monotonic series

- none within any store and count definition

## County sums

- curated doh_dashboard 2026-10-05 (calendar_year): 67 county rows sum to 1004; curated doh_dashboard:592880a918d0 (T1) total 1004 (consistent)
- sensitivity seed_t3_county 2026-08-25 (unknown): 2 county rows sum to 214; sensitivity seed_statewide:sw-m06 (T3-derived) total 393 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-17 (unknown): 9 county rows sum to 629; sensitivity seed_statewide:sw-m07 (T3-derived) total 767 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-21 (unknown): 3 county rows sum to 514; sensitivity seed_statewide:sw-007 (T3-derived) total 792 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-28 (unknown): 3 county rows sum to 552; sensitivity seed_statewide:sw-008 (T3-derived) total 903 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-10-05 (unknown): 9 county rows sum to 604; sensitivity seed_statewide:sw-010 (T3-derived) total 1004 [compared, cross-source, not flagged]

## Count definitions

- 15 statewide rows have count_definition `unknown`: curated:sw-002, curated:sw-003, curated:sw-004, curated:sw-005, curated:sw-006, curated:sw-009, sensitivity:sw-007, sensitivity:sw-008, sensitivity:sw-010, sensitivity:sw-m02, sensitivity:sw-m03, sensitivity:sw-m04, sensitivity:sw-m05, sensitivity:sw-m06, sensitivity:sw-m07
- dashboard 2026-10-05: calendar_year 1004
- dashboard 2026-10-05: since_april 992

## Growth steps

- 134 (2026-07-23, sensitivity sw-m05, T2) -> 379 (2026-08-21, curated sw-003, T1): doubling every 19 days over 29 days. Verify against DOH; do not smooth.

## Values by month (all tiers)

- 2026-06: 61 (2026-06-22, curated sw-002, T1, unknown); 84 (2026-06-26, sensitivity sw-m03, T3-derived, unknown)
- 2026-07: 134 (2026-07-23, sensitivity sw-m05, T2, unknown); 114 (date to confirm, sensitivity sw-m04, T3-derived, unknown)
- 2026-08: 379 (2026-08-21, curated sw-003, T1, unknown); 393 (2026-08-25, sensitivity sw-m06, T3-derived, unknown)
- 2026-09: 676 (2026-09-11, curated sw-006, T1, unknown); 943 (2026-09-30, curated sw-009, T1, unknown); 767 (2026-09-17, sensitivity sw-m07, T3-derived, unknown); 792 (2026-09-21, sensitivity sw-007, T3-derived, unknown); 903 (2026-09-28, sensitivity sw-008, T3-derived, unknown)
- 2026-10: 1004 (2026-10-05, curated doh_dashboard, T1, calendar_year); 992 (2026-10-05, curated doh_dashboard, T1, since_april); 1004 (2026-10-05, sensitivity sw-010, T3-derived, unknown)

## Quarantine

- curated case_state: 2 row(s), DATE_TO_CONFIRM
- curated doh_dashboard: 1 row(s), PARSE_SCHEMA_CHANGE
- sensitivity case_state: 2 row(s), DATE_TO_CONFIRM

_Reference: 67 Pennsylvania counties._
