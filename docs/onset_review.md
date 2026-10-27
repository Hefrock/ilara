# Onset-week curve: how it is revised (for the owner review, ADR 0014 condition 3)

Prepared 2026-10-27 for the review agreed when the Epidemic Curve tab was opened (B18). Observed
data only, no model. Regenerate the tables with `python -m project.validation.onset_review`.
Source: DOH dashboard, Epidemic Curve tab, "Measles Cases by Week", stored as
`case_demographics` dimension `onset_week` (ADR 0015). Weeks start on Monday.

## What we have

Five data dates: 2026-10-16, 19, 21, 23 and 26 (several captures per date; captures of the same
date agree exactly). That is ten days of revisions, which is enough to see the pattern but not
enough to estimate a reporting delay distribution with any confidence.

## The recent weeks, as each data date showed them

| Onset week | Oct 16 | Oct 19 | Oct 21 | Oct 23 | Oct 26 |
|---|---|---|---|---|---|
| Sep 7 | 145 | 145 | 143 | 143 | 143 |
| Sep 14 | 116 | 121 | 122 | 122 | 122 |
| Sep 21 | 105 | 110 | 110 | 111 | 111 |
| Sep 28 | 87 | 93 | 92 | 94 | 94 |
| Oct 5 | 70 | 69 | 80 | 83 | 86 |
| Oct 12 | 22 | 27 | 49 | 62 | 68 |
| Oct 19 | | 6 | 2 | 4 | 16 |
| Oct 26 | | | | | 1 |

Blank: the week had not started, or DOH showed only a placeholder bar (not stored, I5).

## Findings

1. **The last two weeks are far from complete.** The week of Oct 12 tripled between the first
   and last data date (22 to 68) and is still rising. The current week is a handful of cases
   whatever its final size. Read naively, the curve always shows a steep fall in the last two
   weeks; that fall is an artefact of reporting delay, not a sign the outbreak is ending.
2. **About 80% complete two weeks after the week starts, about 95% after three.** For weeks
   old enough to compare (their latest count seen at least 21 days after they started), the
   earlier count as a share of the latest:

   | Seen this many weeks after the week started | Counts | Share of latest (min / median / max) |
   |---|---|---|
   | 1 (7 to 13 days) | 1 | 0.81 |
   | 2 | 4 | 0.80 / 0.93 / 0.97 |
   | 3 | 4 | 0.95 / 0.98 / 1.00 |
   | 4 | 4 | 0.95 / 0.99 / 1.00 |
   | 5 | 4 | 0.99 / 1.00 / 1.01 |

   These are upper bounds: the "latest" count for a three-week-old week is itself still
   growing slightly. Only one count was seen one week after its week started, so the
   first-week figure is a single example.
3. **Counts move both ways.** 30 changes between consecutive data dates, 9 of them decreases
   (the week of Oct 19 went 6, 2, 4, 16; the week of Sep 7 went 145 to 143). Older weeks move
   too: 15 changes to weeks more than four weeks old, none larger than 5 cases. So onset dates
   are corrected after first report, and the stored counts cannot be treated as cumulative or
   as a lower bound.
4. **Where newly reported cases land.** Between Oct 16 and Oct 26 the statewide total rose by
   100 (1,260 to 1,360). About 79 of those went to the weeks from Oct 5 onward, about 17 to the
   four weeks before (Sep 7 to Sep 28, net of corrections), and the rest to older weeks. Most
   newly reported cases had their onset within about three weeks before being reported.

## What this means for the model (for discussion)

The model is fitted to the series by report date: statewide totals and county snapshots on
each data date (I6). The onset curve is not used. Options:

- **A. Keep it out of the model** and use it only as a sanity check on the fitted epidemic
  curve. Nothing to build. The checks above can be rerun each week.
- **B. Use only settled weeks** (three or more weeks old, about 95% complete) as an extra
  observation stream. Simple, but it gives no information about the last three weeks, which is
  where a forecast needs it most.
- **C. Model the delay explicitly** (an onset-based observation model with right truncation:
  each onset week is observed as a growing fraction of its final count). This uses the recent
  weeks properly but needs the delay distribution, and ten days of revisions are too few to
  estimate it. About four more weeks of captures (three updates a week) would give a usable
  estimate.

My recommendation: **A now, revisit C in late November**, once there are about 15 data dates.
Keep the onset curve off the public dashboard until then: shown without the delay explained,
the falling last two weeks would mislead.

## Decisions for the owner

1. Whether the model uses the onset curve now (A, B or C).
2. Whether the public dashboard ever shows it, and with what caveat.
3. Whether to rerun this review on a fixed date (proposed: 2026-11-25).
