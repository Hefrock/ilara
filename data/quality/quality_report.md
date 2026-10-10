# Data quality report

Generated 2026-10-10T01:32:55Z by `measles quality` (engine 1.0.0). Latest dashboard data as of 2026-10-09. Regenerated on every capture run; flags are the durable record (`data_quality_flag`).

Reported counts are a floor. Conflicts below are shown, not resolved (I5). Rows from the sensitivity store (news-derived, secondary) are labelled with their tier and are never used in default views.

## Open flags

- **DATE_TO_CONFIRM** (4)
  - curated: data/seed/statewide_backfill.csv sw-004: date to confirm
  - curated: data/seed/statewide_backfill.csv sw-005: date to confirm
  - sensitivity: data/sensitivity/seed/statewide_t3_derived.csv sw-m01: date to confirm
  - sensitivity: data/sensitivity/seed/statewide_t3_derived.csv sw-m04: date to confirm
- **PARSE_SCHEMA_CHANGE** (1)
  - curated: data/raw/doh_dashboard/2026/20261007T022732Z_f326ab94771c.json.gz: DashboardParseError: no data query responses in the capture
- **SOURCE_CONFLICT** (1)
  - curated: curated case_state 2026-08-25|doh_release|calendar_year: cum_cases 393, counties_with_cases 29 (ccf7dcb81392); cum_cases 393, counties_with_cases 28 (ab7b6de37998)
- **STALE_SNAPSHOT** (3)
  - curated: doh_release: no good capture within 48 h (last good 2026-10-07T20:06:08Z)
  - curated: wayback_cdx: no good capture within 48 h (last good 2026-10-07T11:56:00Z)
  - curated: doh_han_pdf: no good capture within 48 h (last good 2026-10-07T11:55:46Z)

## Capture freshness

- cdc_measles_cases_map: last outcome changed, last good 2026-10-09T19:38:46Z (6 h ago)
- cdc_measles_cases_weekly: last outcome changed, last good 2026-10-09T19:38:51Z (6 h ago)
- cdc_measles_national: last outcome changed, last good 2026-10-09T19:38:31Z (6 h ago)
- cdc_measles_states_config: last outcome unchanged, last good 2026-10-09T19:38:36Z (6 h ago)
- cdc_measles_weekly_config: last outcome unchanged, last good 2026-10-09T19:38:41Z (6 h ago)
- census_cartographic: last outcome unchanged, last good 2026-10-09T19:38:26Z (6 h ago)
- census_commuting: last outcome unchanged, last good 2026-10-09T19:38:19Z (6 h ago)
- census_commuting_index: last outcome changed, last good 2026-10-09T19:38:26Z (6 h ago)
- census_popest_agesex: last outcome unchanged, last good 2026-10-09T19:38:14Z (6 h ago)
- census_popest_totals: last outcome unchanged, last good 2026-10-09T19:38:09Z (6 h ago)
- doh_dashboard: last outcome changed, last good 2026-10-10T01:32:53Z (0 h ago)
- doh_han_index: last outcome unchanged, last good 2026-10-09T19:37:55Z (6 h ago)
- doh_han_pdf: last outcome changed, last good 2026-10-07T11:55:46Z (62 h ago) STALE
- doh_measles_page: last outcome unchanged, last good 2026-10-09T19:37:44Z (6 h ago)
- doh_newsroom: last outcome unchanged, last good 2026-10-09T19:37:49Z (6 h ago)
- doh_release: last outcome changed, last good 2026-10-07T20:06:08Z (53 h ago) STALE
- doh_school_imm_county: last outcome unchanged, last good 2026-10-09T19:37:59Z (6 h ago)
- doh_school_imm_school: last outcome unchanged, last good 2026-10-09T19:38:04Z (6 h ago)
- local_hd_lancaster: last outcome unchanged, last good 2026-10-09T19:38:56Z (6 h ago)
- wayback_cdx: last outcome changed, last good 2026-10-07T11:56:00Z (62 h ago) STALE

## Implied counts

- sensitivity sw-008: 115 new with no start date; no implied count computed (see the weekly comparison below).
- curated doh_release:a5eb00f043e8: implies 424 on 2026-08-26 (460 - 36)
- curated doh_release:234bc9d2bd18: implies 460 on 2026-08-28 (497 - 37)
  - agrees with curated doh_release:a5eb00f043e8 (T1) = 460 on 2026-08-28
- curated doh_release:d397e92aff80: implies 497 on 2026-08-31 (540 - 43)
  - agrees with curated doh_release:234bc9d2bd18 (T1) = 497 on 2026-08-31
  - hint: curated sw-004 (date to confirm) has the same count 497, so it may be as of 2026-08-31
- curated doh_release:6ce22677fdb3: implies 594 on 2026-09-08 (624 - 30)
- curated doh_release:afe524156bc0: implies 624 on 2026-09-09 (676 - 52)
  - agrees with curated doh_release:6ce22677fdb3 (T1) = 624 on 2026-09-09
- curated sw-006: implies 624 on 2026-09-09 (676 - 52)
  - agrees with curated doh_release:6ce22677fdb3 (T1) = 624 on 2026-09-09
- curated doh_release:82bd1a1d894a: implies 676 on 2026-09-11 (693 - 17)
  - agrees with curated doh_release:afe524156bc0 (T1) = 676 on 2026-09-11
  - agrees with curated seed_statewide:sw-006 (T1) = 676 on 2026-09-11
- curated doh_release:ef62d735ed4a: implies 693 on 2026-09-14 (731 - 38)
  - agrees with curated doh_release:82bd1a1d894a (T1) = 693 on 2026-09-14
- curated doh_release:4f1646001515: implies 792 on 2026-09-21 (835 - 43)
  - agrees with sensitivity seed_statewide:sw-007 (T3-derived) = 792 on 2026-09-21
- curated doh_release:2b71da109623: implies 835 on 2026-09-23 (890 - 55)
  - agrees with curated doh_release:4f1646001515 (T1) = 835 on 2026-09-23
- curated doh_release:c8427b621a17: implies 890 on 2026-09-25 (903 - 13)
  - agrees with curated doh_release:2b71da109623 (T1) = 890 on 2026-09-25
- curated doh_release:d79c1b904df0: implies 903 on 2026-09-28 (943 - 40)
  - agrees with curated doh_release:c8427b621a17 (T1) = 903 on 2026-09-28
  - agrees with sensitivity seed_statewide:sw-008 (T3-derived) = 903 on 2026-09-28
- curated sw-009: implies 903 on 2026-09-28 (943 - 40)
  - agrees with curated doh_release:c8427b621a17 (T1) = 903 on 2026-09-28
  - agrees with sensitivity seed_statewide:sw-008 (T3-derived) = 903 on 2026-09-28
- curated doh_release:91b3184e5b08: implies 943 on 2026-09-30 (977 - 34)
  - agrees with curated doh_release:d79c1b904df0 (T1) = 943 on 2026-09-30
  - agrees with curated seed_statewide:sw-009 (T1) = 943 on 2026-09-30
- curated sw-004: implies 460 on 2026-08-28 (497 - 37) (row is quarantined: date to confirm)
  - agrees with curated doh_release:a5eb00f043e8 (T1) = 460 on 2026-08-28
- curated sw-005: implies 497 on 2026-08-31 (540 - 43) (row is quarantined: date to confirm)
  - agrees with curated doh_release:234bc9d2bd18 (T1) = 497 on 2026-08-31
  - hint: curated sw-004 (date to confirm) has the same count 497, so it may be as of 2026-08-31

## Seed conflicts

- sensitivity sw-008: 903 on 2026-09-28 with 115 new in the week implies 788 on 2026-09-21; sensitivity sw-007 (T3-derived) says 792: conflicts

## Source conflicts

- curated case_state 2026-08-25|doh_release|calendar_year: cum_cases 393, counties_with_cases 29 (ccf7dcb81392); cum_cases 393, counties_with_cases 28 (ab7b6de37998)

## Non-monotonic series

- none within any store and count definition

## County sums

- curated doh_dashboard 2026-10-05 (calendar_year): 67 county rows sum to 1004; curated doh_dashboard:592880a918d0 (T1) total 1004 (consistent)
- curated doh_dashboard 2026-10-07 (calendar_year): 67 county rows sum to 1078; curated doh_dashboard:1953c5cca960 (T1) total 1078 (consistent)
- curated doh_dashboard 2026-10-09 (calendar_year): 67 county rows sum to 1136; curated doh_dashboard:d979533cd497 (T1) total 1136 (consistent)
- sensitivity seed_t3_county 2026-08-25 (unknown): 2 county rows sum to 214; sensitivity seed_statewide:sw-m06 (T3-derived) total 393 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-17 (unknown): 9 county rows sum to 629; sensitivity seed_statewide:sw-m07 (T3-derived) total 767 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-21 (unknown): 3 county rows sum to 514; sensitivity seed_statewide:sw-007 (T3-derived) total 792 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-09-28 (unknown): 3 county rows sum to 552; sensitivity seed_statewide:sw-008 (T3-derived) total 903 [compared, cross-source, not flagged]
- sensitivity seed_t3_county 2026-10-05 (unknown): 9 county rows sum to 604; sensitivity seed_statewide:sw-010 (T3-derived) total 1004 [compared, cross-source, not flagged]

## Count definitions

- 15 statewide rows have count_definition `unknown`: curated:sw-002, curated:sw-003, curated:sw-004, curated:sw-005, curated:sw-006, curated:sw-009, sensitivity:sw-007, sensitivity:sw-008, sensitivity:sw-010, sensitivity:sw-m02, sensitivity:sw-m03, sensitivity:sw-m04, sensitivity:sw-m05, sensitivity:sw-m06, sensitivity:sw-m07
- dashboard 2026-10-05: calendar_year 1004
- dashboard 2026-10-05: since_april 992
- dashboard 2026-10-07: calendar_year 1078
- dashboard 2026-10-07: since_april 1066
- dashboard 2026-10-09: calendar_year 1136
- dashboard 2026-10-09: since_april 1124

## Growth steps

- 134 (2026-07-23, sensitivity sw-m05, T2) -> 379 (2026-08-21, curated sw-003, T1): doubling every 19 days over 29 days. Verify against DOH; do not smooth.
- 393 (2026-08-25, sensitivity sw-m06, T3-derived) -> 460 (2026-08-28, curated doh_release, T1): doubling every 13 days over 3 days. Verify against DOH; do not smooth.
- 624 (2026-09-09, curated doh_release, T1) -> 676 (2026-09-11, curated doh_release, T1): doubling every 17 days over 2 days. Verify against DOH; do not smooth.

## Values by month (all tiers)

- 2026-05: 23 (2026-05-06, curated doh_release, T1, calendar_year); 32 (2026-05-22, sensitivity sw-m02, T3-derived, unknown)
- 2026-06: 61 (2026-06-22, curated sw-002, T1, unknown); 84 (2026-06-26, curated doh_release, T1, calendar_year); 84 (2026-06-26, sensitivity sw-m03, T3-derived, unknown)
- 2026-07: 134 (2026-07-23, sensitivity sw-m05, T2, unknown); 114 (date to confirm, sensitivity sw-m04, T3-derived, unknown)
- 2026-08: 379 (2026-08-21, curated sw-003, T1, unknown); 393 (2026-08-25, curated doh_release, T1, calendar_year); 460 (2026-08-28, curated doh_release, T1, calendar_year); 497 (2026-08-31, curated doh_release, T1, calendar_year); 393 (2026-08-25, sensitivity sw-m06, T3-derived, unknown)
- 2026-09: 540 (2026-09-02, curated doh_release, T1, calendar_year); 624 (2026-09-09, curated doh_release, T1, calendar_year); 676 (2026-09-11, curated doh_release, T1, calendar_year); 676 (2026-09-11, curated sw-006, T1, unknown); 693 (2026-09-14, curated doh_release, T1, calendar_year); 731 (2026-09-16, curated doh_release, T1, calendar_year); 835 (2026-09-23, curated doh_release, T1, calendar_year); 890 (2026-09-25, curated doh_release, T1, calendar_year); 903 (2026-09-28, curated doh_release, T1, calendar_year); 943 (2026-09-30, curated doh_release, T1, calendar_year); 943 (2026-09-30, curated sw-009, T1, unknown); 767 (2026-09-17, sensitivity sw-m07, T3-derived, unknown); 792 (2026-09-21, sensitivity sw-007, T3-derived, unknown); 903 (2026-09-28, sensitivity sw-008, T3-derived, unknown)
- 2026-10: 977 (2026-10-02, curated doh_release, T1, calendar_year); 1004 (2026-10-05, curated doh_dashboard, T1, calendar_year); 992 (2026-10-05, curated doh_dashboard, T1, since_april); 1078 (2026-10-07, curated doh_dashboard, T1, calendar_year); 1066 (2026-10-07, curated doh_dashboard, T1, since_april); 1136 (2026-10-09, curated doh_dashboard, T1, calendar_year); 1124 (2026-10-09, curated doh_dashboard, T1, since_april); 1004 (2026-10-05, sensitivity sw-010, T3-derived, unknown)

## Quarantine

- curated doh_dashboard: 3 row(s), PARSE_SCHEMA_CHANGE
- curated case_state: 2 row(s), DATE_TO_CONFIRM
- sensitivity case_state: 2 row(s), DATE_TO_CONFIRM

_Reference: 67 Pennsylvania counties._
