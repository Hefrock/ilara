# Backfill report (WP3c, T3.12)

Outcome of the backfill so far. Documents are listed in `data/registry/backfill_urls.yml` and
captured through the raw store by `measles capture --backfill` (first run: capture
`gh-37617137202-1`, 2026-10-07). Release figures are parsed into `case_state` with source
`doh_release` (tier T1); seed files are never edited (corrections are new seed files).

## Register items

| Item | Outcome | Evidence |
|---|---|---|
| U11 Wayback CDX technique | **Works.** One CDX query returned 529 archived DOH newsroom URLs, 30 about measles, including statewide updates not linked from the measles page. Their live URLs were added to the backfill list. | `data/raw/wayback_cdx/`; `data/registry/backfill_urls.yml` |
| U14 HAN 822 PDF URL | **Open.** The HAN index page loads its list in the browser, so the captured HTML has no PDF links, and the Wayback index query covered the newsroom only. Next: a CDX query for `pa.gov/content/dam/copapwp-pagov/en/health/documents/topics/documents/2026%20HAN/*`. | `data/raw/doh_han_index/` |
| U16 Release dates for 497 and 540 | **Resolved.** 497 in 34 counties is the release of 2026-08-31 (37 new since Aug 28); 540 in 36 counties is the release of 2026-09-02 (43 new since Aug 31). The seed rows sw-004 and sw-005 stay quarantined as seeded; the dated T1 rows now come from the releases. DOH releases for 903 (2026-09-28) and 676 (2026-09-11) were also captured; the releases for 792 (Sep 21) and 1,004 (Oct 5) are queued in the backfill list. | `doh_release` rows in `data/curated/case_state/` |
| U17 Count definition for 379 and later values | **Partly resolved.** Every statewide release says "so far in 2026" (or "in 2026 so far", "thus far in 2026"), so release counts are calendar-year totals. The dashboard states its definition directly from 2026-10-05. HAN 838 (379 as of Aug 21) is captured; its wording is still to be read (needs PDF text extraction). | `docs/probe_report.md`; release parser |

## Seed rows and conflicts

- **792 vs 788 (T3.8):** the 788 came from a news figure of "115 new in the week". The DOH
  release of 2026-09-28 gives "New Positive Cases (since September 25, 2026): 13", not 115. The
  news figure is not supported by the release; the quality report keeps both values visible.
- **Aug 25, 28 vs 29 counties:** two DOH releases of the same day give 393 cases, one in 28
  counties and one in 29. Flagged `SOURCE_CONFLICT`; not resolved by hand.
- **News-derived values with T1 corroboration:** 84 on 2026-06-26 (sw-m03), 393 on
  2026-08-25 (sw-m06) and 903 on 2026-09-28 (sw-008) match DOH releases of those dates. The
  May 6 release says 23 cases in 2026 "including 12 individuals from prior unrelated cases
  reported earlier this year", which supports the January to March figure of 12 (sw-m01).
  The sensitivity rows stay where they are; the T1 values exist separately in curated.

## Event URLs found (`url_to_find` to `verified`)

Added as `data/seed/events_urls_2026-10-07.csv` (new rows for the same `event_id`; the current
view takes the newer row). Each match was checked by release date and wording.

| Event | Release |
|---|---|
| ev-007 dashboard launched (2026-07-14) | shapiro-administration-launches-measles-dashboard |
| ev-010 pop-up clinics (2026-09-11) | department-of-health-provides-statewide-update-091126 |
| ev-014 Lancaster exposure (2026-05-29) | department-of-health-responding-to-potential-measles-exposure |
| ev-015 Lancaster County Courthouse (2026-06-12) | doh-responding-to-measles-exposure-at-lancaster-courthouse |
| ev-016 Snyder County Lowe's (2026-07-22) | pennsylvania-department-of-health-responding-to-potential-measle |
| ev-017 two Lancaster locations (2026-08-19) | doh-responding-to-two-separate-potential-measles-exposures-in-la |
| ev-018 Westmoreland exposure (2026-09-02) | dept-of-health-responding-to-potential-measles-exposure-in-westm |

Still `url_to_find`: ev-002 (HAN 822), ev-003 (HAN 830), ev-006 (HAN 831 recommendations,
URL known for HAN 831 itself), ev-013 (the May 6 release does not mention the Lebanon clinic).

## Not yet done

- Read the HAN PDFs (817, 831, 838): needs a PDF text dependency.
- Parse the releases queued from the Wayback index once captured.
- T3 events (school opening, dose counts) still need T1 corroboration.
