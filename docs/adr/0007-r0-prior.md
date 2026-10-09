# ADR 0007: R0 prior from the Guerra 2017 review

Status: accepted (agent decision within WP6; the owner may override).

## Context

The simulator needs a prior range for the basic reproduction number R0, narrowed later by
calibration (6c). The often cited 12 to 18 traces to Anderson and May. The systematic review by
Guerra et al. 2017 (https://doi.org/10.1016/S1473-3099(17)30307-9, read from the full text, figures
in `docs/references/README.md`) found 58 estimates from 18 studies, only 10 of them within 12 to 18,
and recommends estimates from similar settings rather than one value.

The outbreak in Pennsylvania is a vaccine-era outbreak in a developed country, concentrated in
communities with low coverage. The closest settings in the review:

- developed countries, vaccine era: median 11.7 (6 publications, 10 estimates);
- Americas: median 15.3 (3 publications, 4 estimates);
- outbreak data: median 9.9 (4 publications, 8 estimates);
- Glasser et al. 2016, a 2008 school outbreak in California: 10.7 assuming a well-mixed
  population and 18.1 with school-specific mixing.

## Decision

`r0` is uniform from 9.9 to 18.1 in `project/model/params.yml`. Both bounds are cited estimates
(the outbreak-data median and the structured US estimate), and the range contains the other
setting medians above. Values far outside it (for example the 27.0 maximum for the Americas) come
from pre-vaccine surveillance with different methods and are not used.

## Consequences

- The prior is wider at the low end than 12 to 18. The U19 sensitivity output (T6.2) therefore
  includes more runs below the epidemic threshold for a given susceptible share.
- The prior describes plausible values, not a Pennsylvania estimate. Calibration (6c) on the
  Pennsylvania series, after Gate G3, decides what the data support; posterior and prior are
  reported side by side.
- Our model mixes homogeneously within a county, closer to Glasser's well-mixed value; clustering
  of susceptibles enters through the U19 scenarios instead. This is why the upper bound uses the
  structured estimate only as an outer limit.
