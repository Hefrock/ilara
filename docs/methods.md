# Methods

How the data are collected and curated, and how the model is built, fitted and validated, as of
2026-11-11. A [review](methods_review_2026-11.md) of these methods lists known weaknesses.
Decisions and their reasons are in the ADRs
under [adr/](adr/), sources in [sources.md](sources.md), table layouts in
[schemas.md](schemas.md), and the build plan in [HANDOFF.md](HANDOFF.md). Every number below
that comes from a run cites its ADR; nothing here is a forecast.

## 1. Data

**Sources and tiers.** T1 is official primary data: the PA Department of Health (DOH) measles
dashboard and press releases, CDC, Census. T2 is peer-reviewed literature. T3 is news, used only
to find sources and sanity-check them. `T3-derived` figures (dashboard values quoted in news,
which the dashboard itself does not keep) live under `data/sensitivity/` and never enter the
default fit, charts or public site.

**Capture.** Scheduled GitHub Actions workflows load the DOH dashboard on its Monday, Wednesday
and Friday publishing days, after its refresh at about 13:00 to 14:20 ET
([ADR 0010](adr/0010-capture-timing-from-refresh-times.md)). One navigation per capture; the
capture clicks only the visible report tabs and refuses any response with case or record
identifiers. Every outcome is logged, and changed content is saved raw with a hash before
anything else is done with it. A capture that reaches a dead or unavailable report counts as
failed ([ADR 0009](adr/0009-dead-dashboard-link-and-g2-tracker.md)). GitHub starts scheduled runs
late, so a backup routine starts a capture when the day's update has not been captured
([ADR 0006](adr/0006-dashboard-capture-backup-trigger.md)), and a publishing day counts as covered
by a good capture from 18:00 UTC that day to 06:00 UTC the next
([ADR 0027](adr/0027-g2-cover-window-to-0600-utc.md)). When the department skips an update, as on
the 2026-11-11 holiday, the capture records the unchanged report and no snapshot carries that
date.

**Curation.** Parsers turn raw files into append-only curated tables; every row carries its
source, tier, as-of date, fetch time, raw hash and parser version. Revisions are new rows. The
whole curated store can be rebuilt from raw and seed files and is checked to be identical.
Counts are cumulative by report date; there are no onset dates and no case-level data. A
missing count is a gap, never a zero, and nothing is interpolated.

**Reference data.** Census 2025 county population estimates and age-sex tables, 2024
cartographic boundaries (adjacency and distances), and ACS 2016-2020 county-to-county commuting
flows (2,206 county pairs).

## 2. Susceptibility (WP6a)

Per county, the effective susceptible fraction is built from school immunization coverage
(kindergarten, grade 7 and grade 12, with exemptions and suppressed cells handled
deterministically; children not up to date are treated as unvaccinated), an infant share that
is all susceptible, and an adult immune share drawn between 0.92 and 0.98. Vaccine
effectiveness is 93 percent for one dose and 97 percent for two. Uncertainty enters as seeded
draws. An explicit under-covered subpopulation (U19) is available as scenarios; the default is
none, by owner decision. Post-outbreak doses reported by DOH are converted to immunity gained,
excluding early infant doses from the routine series
([ADR 0004](adr/0004-vaccine-doses-table.md)).

## 3. Simulator (WP6b)

A stochastic chain-binomial county SEIR model for all 67 counties
([ADR 0005](adr/0005-county-seir-simulator.md), [ADR 0008](adr/0008-simulator-inputs-from-events.md)):

- latent period 7 days and infectious period 8 days, each as four Erlang stages, giving a
  generation time of about 12 days ([ADR 0005](adr/0005-county-seir-simulator.md); literature in
  [references](references/README.md));
- R0 prior 9.9 to 18.1 ([ADR 0007](adr/0007-r0-prior.md));
- seeding in every county with a known case, `lead_days` before its first known date; counties
  first seen only at the first county snapshot share one fitted lead before it
  ([ADR 0022](adr/0022-seed-every-county-censored-lead.md));
- intervention and health-alert events reduce transmission in their counties after a lag, by
  factors that are fitted, not assumed;
- post-outbreak vaccination moves people out of the susceptible pool. DOH reports doses
  statewide, so they are spread over counties with a known case, in proportion to population
  (an assumption, [ADR 0012](adr/0012-pennsylvania-calibration-problem.md));
- the school-term effect is off (U24) until a term pattern is seen in the data.

## 4. Calibration (WP6c)

ABC population Monte Carlo ([ADR 0011](adr/0011-calibration-abc-smc.md)). Each candidate
parameter set simulates an epidemic, then reports it: a share `rho` of infections is reported,
after a gamma delay (11.5 days to rash plus a reporting delay), with fewer reports at weekends,
and with negative binomial noise on the increase between consecutive snapshots. Candidates are
kept when their simulated increases are close to the observed ones.

Fitted: R0 (9.9 to 18.1), `lead_days` (7 to 42), `censored_lead_days` (14 to 150), the intervention and health-alert factors,
ascertainment, reporting delay, weekend factor and dispersion. Observations are the T1 county
snapshots plus the statewide counts in DOH releases before the first snapshot. A county count
that DOH later revised down is superseded by the revision and left out of the fit as a gap,
unchanged ([ADR 0020](adr/0020-superseded-snapshots-fit-guards-vaccine-chart.md)). Counties with
fewer than 10 cases at the origin are fitted as one group, so the distance is not dominated by
counties with nothing to match
([ADR 0021](adr/0021-conditioned-forecasts-and-pooled-small-counties.md)). Every county with
a known case is seeded before its first known date; counties first seen only at the first county
snapshot share one calibrated lead before it
([ADR 0022](adr/0022-seed-every-county-censored-lead.md)).

Checks on synthetic data:

- recovery across 20 three-county datasets: every parameter's 90 percent interval held the
  truth in at least 16 of 20 (T6.10);
- two 67-county dry runs, the second on the real statewide reporting dates: all 90 percent
  intervals held the truth; R0 narrowed to about 13 to 18, while seeding time, ascertainment and
  reporting delay stayed wide
  ([ADR 0012](adr/0012-pennsylvania-calibration-problem.md)).

Real county data are not fitted before Gate G3 (ten county snapshot dates), which passed on
2026-10-28. Real fits have run at weekly origins since then, as model version 1; their outputs
are private before Gate G4. The fitted R0 reflects growth given nearly uniform county
susceptibility and is not an estimate of measles R0 ([review](methods_review_2026-11.md),
finding 4).

Running it. `python -m project.model.preflight --origin <date>` runs the real path up to the
gate without fitting: it counts the snapshot dates, builds the inputs, checks the gate, and times
a simulation (0.01 s each on 2026-10-27, so a fit takes minutes). Once G3 passes,
`python -m project.model.pa --origin <date>` fits the data known at that origin's cutoff and
writes the posterior, predictive checks, forecast samples and a manifest under
`project/outputs/` (gitignored, never public before G4). The onset-week curve is not used; see
[the onset review](onset_review.md).

## 5. Validation (WP6d)

At weekly origins from 2026-10-28, the model is refitted on data fetched by the end of that day
and forecasts cases newly reported in each of the next four weeks, per county and statewide,
by continuing the accepted simulated epidemics past the origin
([ADR 0013](adr/0013-forecast-validation-and-g4-gate.md), ADR 0021). Each score carries the
model version that made it; a changed model is a new version, scored only from then on
([ADR 0026](adr/0026-release-time-release-backup-model-version.md)). Forecasts are scored with the
weighted interval score and the coverage of their 50, 80 and 90 percent intervals, against a
persistence baseline on the same targets. Any read of data fetched after an origin stops the
run. Forecasts are published only if, over at least eight origins pooled across counties, the
80 percent interval covers 70 to 90 percent of outcomes and the score beats persistence at one
and two weeks (Gate G4). The earliest that decision could be made was 2026-12-30; a skipped
update on 2026-11-11 leaves targets unscored under the current rules, and the coverage and
baseline tests have known flaws ([review](methods_review_2026-11.md), findings 1 to 3). Revised
scoring rules are proposed in [ADR 0028](adr/0028-scoring-rules-proposed.md) and are not in
force.

## 6. Limitations

- Counts are a floor: they are cases known to and published by DOH.
- The dashboard keeps no history. It launched on 2026-07-14; the series exists only from our
  captures (from 2026-10-05) and dated DOH releases before that, so about 36 updates were never
  archived ([ADR 0023](adr/0023-end-of-outbreak-plan.md), item 6).
- County susceptibility is nearly uniform and each county mixes evenly, so concentrated
  under-vaccinated communities are not represented.
- With no line list or onset dates, ascertainment, reporting delay and seeding time are weakly
  identified.
- Commuting flows are from 2016-2020 and describe workers, not the community most affected.
- School coverage is a December 2025 baseline; coverage in the most affected community is not
  measured directly (U19).
