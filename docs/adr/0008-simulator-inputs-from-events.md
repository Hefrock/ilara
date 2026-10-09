# ADR 0008: simulator inputs from events and county data

Status: accepted (agent decision within WP6b; the owner may override).

## Context

HANDOFF 6b asks for a school-calendar covariate, intervention effects from `event` rows, and
seeding from observed first-case dates. The data hold 15 events and two county snapshots
(Oct 5 and 7). No `school_calendar` event exists in the default store, and no event records an
intervention with a measured effect. Event types do not say whether a county had cases: HAN 830
(Delaware) reports wastewater detection only.

## Decision

`project/model/inputs.py` builds three (days, counties) arrays, reading only through
`ingest.access`, optionally as known at a time (replay, E11). Parameters are in
`project/model/params.yml`, all ASSUMPTION and to be calibrated in 6c.

- School calendar: `school_calendar` events with titles `term_start`, `term_end`,
  `break_start`, `break_end` (`SCHOOL_CALENDAR_TITLES`). Out of session, transmission is
  multiplied by `1 - share`. Where no event says whether school is in session, no adjustment is
  made and the gap is reported. `share` is 0 until district calendars are recorded (U24).
- Interventions: for each event type listed (`intervention`, `health_alert`), a factor from
  `event_date + lag_days` in the event's counties. Factors default to 1 (no effect);
  calibration estimates them within [low, 1]. `affected_counties` means counties with a known
  case by the event date. Vaccination enters through doses, not these factors.
- Seeding: `first_known` gives, per county, the earliest date a source shows an infectious
  case there: an alert listed by ID because its text states cases (ev-001, ev-002), an exposure
  notice (presence, not residence), or the first county snapshot with cases. A county first
  seen in the first snapshot captured is marked censored. Fixed exposures are placed
  `lead_days` before that date: the earliest county only by default, every county as a
  sensitivity variant. The simulator takes them as a new `seeds` input.

## Consequences

- Nothing is inferred where the data are silent: unknown calendar periods, unresolved scopes
  and censored first dates are listed in `Inputs.notes` (I5). First known dates are upper
  bounds by construction, never onset dates (I6).
- With the defaults the inputs change nothing but the seeding: the model is unchanged until
  calibration or new events say otherwise.
- The T3 sensitivity event "First Lancaster County schools open" is not in the calendar
  vocabulary, so a sensitivity run that includes it is refused rather than reinterpreted.
- Most counties' first known dates come from the first snapshot (censored); more snapshots and
  dated T1 statements will improve seeding for `all` mode.
