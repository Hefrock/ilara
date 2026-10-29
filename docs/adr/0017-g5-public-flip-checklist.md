# ADR 0017: Gate G5 (public flip) checklist and known exceptions

Status: open checklist (owner, 2026-10-23: "add the Lancaster key note to the G5 checklist").
HANDOFF section 5 places the G5 checklist in `docs/adr/`; this is it. Every item must be
checked, with evidence, before the owner decides B11 (the irreversible flip).

## Checklist (HANDOFF section 5, G5)

- [ ] Four consecutive weeks clean (G2 sustained). Evidence: G2 tracker in
      `data/quality/quality_report.md`.
- [ ] Licence review.
- [ ] Secret scan over full history passes, with only the known exceptions below.
- [ ] Hygiene scan over full history passes (scope as T0.5, which ignores `data/raw/`).
- [ ] H6 decision (sensitivity seeds in history, B05) re-confirmed.
- [ ] README notice present (T7.1).
- [ ] Scheduled-workflow behaviour for public repositories checked against current GitHub
      documentation (U21, U23).
- [ ] B13 decided: how to treat the first commit's author metadata.
- [ ] Licence for the documentation and the curated data decided (the code is MIT), so the
      archive can be reused for teaching (owner, 2026-10-29).
- [ ] Archiving decided: whether a release is deposited with a DOI (for example through Zenodo),
      which publishes that snapshot permanently, and which release (owner, 2026-10-29; see the
      end-of-outbreak plan, ADR 0023).

## Known exceptions

### E1. Google Maps browser key in Lancaster County health department captures

- **What:** the Lancaster County health department website (a CivicPlus site) publishes a
  Google Maps browser API key in a hidden field on every page it serves
  (`<input type="hidden" id="GoogleMapsKey" value="…">`). Our raw captures of that page
  (`data/raw/local_hd_lancaster/`, first committed in `34ea8da` on 2026-10-07 by the capture
  bot) therefore contain it, verbatim. Every capture of the page will keep containing it while
  the site publishes it; on 2026-10-23 eight files did.
- **Why it is not a project secret:** it is not a credential of this project, it is sent to
  every visitor of the county's site, and browser map keys are meant to be public (Google
  expects site owners to restrict them by referrer). Nothing of ours is exposed.
- **Why it stays:** raw files are immutable and saved verbatim (I1), and history is never
  rewritten. Removing it would not hide it: it is on the county's live site.
- **Detection:** GitHub secret scanning raised it as alert #1. Our own hygiene scan skips
  `data/raw/` by design (T0.5), so it does not.
- **At G5:** confirm that the full-history secret scan finds no secret other than this key,
  and that GitHub's alert is closed as "won't fix" with this ADR as the reason. The key value is
  never copied into the repository, issues or docs.
- **Optional, owner's call:** tell Lancaster County that the key is exposed, if it is not
  restricted to their domain. Contacting an agency is the owner's decision (CLAUDE.md).
