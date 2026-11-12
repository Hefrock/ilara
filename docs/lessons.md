# Lessons from building Ilara

What went wrong while archiving and modelling the 2026 Pennsylvania measles outbreak, written for
students of outbreak epidemiology. Each lesson says what happened, why it matters, how it was
caught and what changed. The technical detail, with dates and numbers, is in the decision record
linked from each one. Nothing here goes beyond what those records say.

## Collecting the data

### 1. A dashboard with no history

The Department of Health publishes its figures on a dashboard that shows only the latest numbers.
An update that is not captured on the day it appears is gone for good. GitHub's scheduler, which
runs the captures, sometimes started hours late or not at all.

*Why it matters:* most public outbreak data is published this way. If no one keeps the history,
no one can later ask what was known on a given day.

*What changed:* every capture is saved exactly as received, with a hash, before anything else
happens to it, and backup routines start a capture when the scheduled one is missing.
[ADR 0006](adr/0006-dashboard-capture-backup-trigger.md).

### 2. A capture that succeeded but held nothing

On 13 October 2026 the department moved its dashboard to a new link. Our captures kept "working":
they reached a placeholder page saying the content was not available, and recorded that as a
normal capture. The day looked covered, so no backup ran.

*Why it matters:* a pipeline that reports success is not the same as a pipeline that collected
data. Checks have to look at what was captured, not only whether the job finished.

*What changed:* a capture that does not reach the report now counts as failed, and the
department's own measles page is watched for a changed dashboard link.
[ADR 0009](adr/0009-dead-dashboard-link-and-g2-tracker.md).

### 3. The same dashboard, redesigned three times

Between 13 and 28 October the dashboard was rebuilt three times: a new report, then new tables
for counties and hospitalisations, then a new table for vaccine doses. Each time the parser no
longer found what it expected, and some figures went unrecorded until it was updated.

*Why it matters:* published data changes shape without notice. Because the raw captures were kept,
every missed figure was recovered once the parser caught up; without them it would have been lost.

*What changed:* parsers are tested on real captures, a format change opens an alert, and a
corrected parser re-reads every past capture automatically.
[ADR 0014](adr/0014-epidemic-curve-tab.md),
[ADR 0018](adr/0018-dashboard-county-v3-hospitalizations-mixed-loads.md),
[ADR 0020](adr/0020-superseded-snapshots-fit-guards-vaccine-chart.md).

### 4. One page, three different days

On 26 October one capture showed headline figures from 16 October next to county figures from
that day and hospitalisation figures from 21 October. The department was part-way through an
update.

*Why it matters:* a single snapshot can disagree with itself. Taken at face value it would have
recorded false counts under the wrong date.

*What changed:* every chart is checked against the totals of the same capture. A set that does not
add up is labelled and kept out of the model; a later, consistent capture records the day
properly. [ADR 0018](adr/0018-dashboard-county-v3-hospitalizations-mixed-loads.md).

### 5. The same data, two different answers

Re-reading all captures after a parser change held back 271 genuine county rows that a rebuild
from scratch kept. The check compared each capture with what was in the store at the time of the
re-read, which already contained the mixed capture from lesson 4, not with what was known when
the capture was taken.

*Why it matters:* any check that looks at "the latest data" has to mean the latest data at that
moment. Otherwise the result depends on the order in which things are processed.

*What changed:* each capture is now judged only against what was known when it was fetched.
[ADR 0020](adr/0020-superseded-snapshots-fit-guards-vaccine-chart.md).

### 6. A schedule that runs late

The captures run on GitHub's free scheduler. Runs started one to three hours late, and one slot
never ran at all. Moving the slots earlier and off the hour helped for a while. Then on 2 November
all four Monday runs succeeded, but five to six hours late, after midnight UTC, where the rule for
a "covered" day no longer counted them.

*Why it matters:* a free scheduler promises no start time. A rule written against the clock fails
when the clock slips, even though the data were captured.

*What changed:* the rule now follows when the data actually change. The department updates only on
Monday, Wednesday and Friday afternoons, so a capture made before 06:00 UTC the next morning still
shows that day's update, and it counts.
[ADR 0025](adr/0025-dashboard-slots-off-peak.md), [ADR 0027](adr/0027-g2-cover-window-to-0600-utc.md).

### 7. A missing chart that stopped the release

When the department republished its report, the chart of cases by month of report was gone. The
weekly release tagged its data, then crashed while building the public dashboard, because the code
expected that table to exist. The tag looked like a finished release; the dashboard was never
built.

*Why it matters:* a source dropping a figure is normal. A pipeline that treats it as impossible
fails at the worst moment, and a step that succeeded first can hide the failure of the next.

*What changed:* each part of the dashboard now says plainly when the latest snapshot does not give
it, and nothing is filled in. [PR 55](https://github.com/Hefrock/ilara/pull/55).

## Reading the data

### 8. The last two weeks always look like a decline

Cases are counted by the week symptoms began, and each week's count keeps rising for about three
weeks as reports arrive. The week of 12 October went from 22 cases to 68 over ten days. Read
naively, the latest weeks always suggest the outbreak is ending.

*Why it matters:* this is right truncation, one of the most common ways outbreak curves mislead.

*What changed:* the onset curve is kept out of the model and the public dashboard until its delays
can be modelled. [ADR 0015](adr/0015-onset-week-series.md), [onset review](onset_review.md).

### 9. Counts that go down

The department sometimes revises a county's count downwards, for example when cases are reassigned
to another county. The first real model fit met two such revisions, could not compare them, and
quietly returned its starting assumptions as if they were results.

*Why it matters:* cumulative counts are not guaranteed to rise, and a model can fail without
saying so.

*What changed:* a count that the department later revised down is left out of the fit rather than
changed, and the fit now stops with an error instead of returning a silent non-answer.
[ADR 0020](adr/0020-superseded-snapshots-fit-guards-vaccine-chart.md).

## Modelling

### 10. Forecasts that died out

The model is stochastic: the same settings can produce an outbreak that fades out or one that
takes off. The fit kept settings together with the simulated epidemic that matched the data, but
the forecasts restarted a fresh simulation instead. More than half of those fresh runs died out,
and the forecast's middle value was zero new cases a week while about 85 were being reported.

*Why it matters:* a forecast has to continue the epidemic that matched what was seen, not a new
one.

*What changed:* forecasts continue each matched simulation, and counties with almost no cases are
fitted as one group so they no longer outweigh the counties driving the outbreak.
[ADR 0021](adr/0021-conditioned-forecasts-and-pooled-small-counties.md).

### 11. One spark for many fires

The model started the epidemic in one county and relied on commuting to carry it elsewhere. The
outbreak had several separate centres, so most simulations never reached the counties that were
growing fastest.

*Why it matters:* how an outbreak starts, and where, shapes everything after. Many of those
counties were first seen only in the first county-level report, so their start dates are unknown;
guessing them would have been fabrication.

*What changed:* every county with a known case now starts its own epidemic, and the unknown start
for the counties first seen in that report is estimated from the data as one shared value.
[ADR 0022](adr/0022-seed-every-county-censored-lead.md).

## Judging the work

### 12. Changing the rule after seeing the score

Gate G2 asks for two weeks in a row in which scheduled runs covered every update day. Widening the
window (lesson 6) and applying it to past weeks would have passed the gate at once. It was applied
only from 2 November, so the gate has to be earned under the rule as it now stands.

*Why it matters:* changing a success rule after seeing the results is one of the quietest ways to
fool yourself. The same holds for forecasts: the model is fixed before it is scored.

*What changed:* rule changes apply going forward, and the record says so.
[ADR 0027](adr/0027-g2-cover-window-to-0600-utc.md), [ADR 0026](adr/0026-release-time-release-backup-model-version.md).

### 13. A holiday is not a gap

On Wednesday 11 November, a state holiday, the department did not update its dashboard. Our
captures ran and recorded the unchanged report, so nothing was missed. But the forecast scoring
expected a snapshot dated on every Wednesday, and without one it could not score several
forecasts, including every forecast made that day.

*Why it matters:* "no new data" and "data not collected" look the same in a table of dates. Only
a record of what was looked at, and when, tells them apart. And a scoring rule that assumes the
source never skips a day will break on the first holiday.

*What changed:* a review of the methods found this and other weaknesses in the scoring rules, and
revised rules were proposed for the owner's decision.
[Methods review](methods_review_2026-11.md), [ADR 0028](adr/0028-scoring-rules-proposed.md).

## The thread through all of them

Keep what was published, exactly, with the date you saw it. Judge every step by what was known at
the time, and by rules set before the results. When something does not add up, label it and leave
it out rather than fix it by hand. And make failures loud.
