# References for model priors (B17, U12, U13)

Only citations, the figures used and short quotes locating them are kept here. Abstracts and
article text are not committed (I10). Records are fetched by the manual `references` workflow
(`measles references`) from Europe PMC; PubMed E-utilities is disallowed by NCBI's robots.txt
for this client and is not used (I7).

| Key | Citation | DOI | What the source says (observed) | Status |
|---|---|---|---|---|
| klinkenberg2011 | Klinkenberg D, Nishiura H. The correlation between infectivity and incubation period of measles, estimated from households with two cases. J Theor Biol. 2011. PMID 21704640 | 10.1016/j.jtbi.2011.06.015 | Abstract: the mean incubation period and the generation time of measles "both lie in the range of 11-12 days" | VERIFIED 2026-10-08 (run gh-37860465223) |
| guerra2017 | Guerra FM, Bolotin S, Lim G, et al. The basic reproduction number (R0) of measles: a systematic review. Lancet Infect Dis. 2017. PMID 28757186 | 10.1016/S1473-3099(17)30307-9 | Abstract: R0 "is often cited to be 12-18"; 18 studies gave 58 estimates; "R0 estimates vary more than the often cited range of 12-18". The medians by setting are in the article body, not the abstract | PARTIAL 2026-10-08: the 12-18 range is a convention the review says is too narrow; the review's own medians still to read |
| vink2014 | Vink MA, Bootsma MCJ, Wallinga J. Serial intervals of respiratory infectious diseases: a systematic review and analysis. Am J Epidemiol. 2014;180(9):865-875 | 10.1093/aje/kwu209 | Not yet read: the PMID first used (25262286) returned an unrelated paper, caught by the DOI check; now looked up by DOI | to read |

## What this means for the model

- Generation time 11 to 12 days (klinkenberg2011). The simulator's stays are geometric, so its
  mean generation time is latent plus infectious period, 8 + 8 = 16 days, too long. A fixed or
  multi-stage infectious period of 8 days gives about 8 + 4 = 12 days. This needs a model change
  before calibration (6c): see `project/model/params.yml`.
- R0: keep 12 to 18 as UNVERIFIED and treat it as too narrow (guerra2017) until the review's
  medians by setting are read.
