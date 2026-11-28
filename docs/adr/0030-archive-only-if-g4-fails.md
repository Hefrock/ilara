# ADR 0030: archive-only if model version 1 fails Gate G4

Status: **accepted** (owner, 2026-11-28: "Proceed with option a").

## Context

Gate G4 decides whether forecasts are published (HANDOFF section 6, as amended by
[ADR 0028](0028-scoring-rules-proposed.md)). With outcomes frozen 14 days after each week, the
earliest decision is after 2027-01-13, when the eighth origin's (2026-12-16) two-week target
freezes. On the four origins scored by 2026-11-26, version 1 loses to persistence in most groups
and its 80 percent intervals are too wide, so a fail is the likely outcome. Model version 2 is
paused ([ADR 0029](0029-model-version-2-plan.md)).

HANDOFF section 10 already allows a recorded fail: forecasts stay withheld and the limitations
section says why. What it left open is whether model work continues afterwards. Three options
were put to the owner on 2026-11-28: (A) archive-only, (B) keep scoring version 1 weekly, (C) a
new model version.

## Decision

Option A.

1. **The decision.** At the first weekly check-in after 2027-01-13, validation is run for model
   version 1 over all origins from 2026-10-28. The check-in reports the G4 result to the owner
   and proposes a pull request that writes `data/validation_gate.json` with `--write-gate`. The
   gate file is written only through that pull request, which the owner merges.
2. **If G4 passes,** forecasts are published as HANDOFF D07 and G4 set out, with the "model
   output, not official guidance" label. This ADR does not apply.
3. **If G4 fails,** once the gate file is merged:
   - the weekly model fits and the weekly forecast check-in stop;
   - forecasts and the watchlist map stay out of every public build, and model outputs stay in
     `project/outputs/` (gitignored, I10);
   - `docs/methods.md` section 6 states the negative result: the model did not beat
     persistence, with the reasons (each county mixes evenly, so Lancaster's simulated outbreak
     burns out; version 2's community group did not fix it; no onset dates or line list);
   - the capture, the archive, the weekly releases and the observed-data dashboard continue as
     before, and the end-of-outbreak plan ([ADR 0023](0023-end-of-outbreak-plan.md)) decides
     when capture stops.
4. **Not reopened by this ADR.** A later model attempt (option C), for example after the DOH
   county counts for July to October arrive, would need a new owner decision, a new frozen model
   version and origins after its freeze (ADR 0026). The G4 result for version 1 stands as
   recorded.

## Consequences

- No code changes now. The weekly check-in's scheduled prompt gains the step in item 1 and the
  stop rule in item 3.
- A recorded negative result is a deliverable of a provenance-first project, not a gap.
