# References for model priors (B17, U12, U13)

Only citations, the figures used and short quotes locating them are kept here. Abstracts and
article text are not committed (I10). Records are fetched by the manual `references` workflow
(`measles references`) from Europe PMC; PubMed E-utilities is disallowed by NCBI's robots.txt
for this client and is not used (I7). Every reference is identified by its DOI, which
`references.yml` holds and the fetcher checks against the record returned; links below resolve
through doi.org.

| Key | Citation | DOI | What the source says (observed) | Status |
|---|---|---|---|---|
| klinkenberg2011 | Klinkenberg D, Nishiura H. The correlation between infectivity and incubation period of measles, estimated from households with two cases. J Theor Biol. 2011. PMID 21704640 | [10.1016/j.jtbi.2011.06.015](https://doi.org/10.1016/j.jtbi.2011.06.015) | Abstract: the mean incubation period and the generation time of measles "both lie in the range of 11-12 days" | VERIFIED 2026-10-08 (run gh-37860465223) |
| guerra2017 | Guerra FM, Bolotin S, Lim G, et al. The basic reproduction number (R0) of measles: a systematic review. Lancet Infect Dis. 2017. PMID 28757186 | [10.1016/S1473-3099(17)30307-9](https://doi.org/10.1016/S1473-3099(17)30307-9) | Abstract: R0 "is often cited to be 12-18"; 18 studies gave 58 estimates; "R0 estimates vary more than the often cited range of 12-18". The medians by setting are in the article body, not the abstract | PARTIAL 2026-10-08: the 12-18 range is a convention the review says is too narrow; the review's own medians still to read |
| vink2014 | Vink MA, Bootsma MCJ, Wallinga J. Serial intervals of respiratory infectious diseases: a systematic review and analysis. Am J Epidemiol. 2014;180(9):865-875 | [10.1093/aje/kwu209](https://doi.org/10.1093/aje/kwu209) | Abstract: mean serial interval for measles "11.7 days" (household outbreak data reanalysed with a common method). The PMID first used (25262286) returned an unrelated paper, caught by the DOI check; found by DOI | VERIFIED 2026-10-08 (run gh-37861236213, DOI match) |

## What this means for the model

- Generation time 11 to 12 days (klinkenberg2011), serial interval 11.7 days (vink2014). The
  simulator's stays were geometric, giving a mean generation time of latent plus infectious
  period, 8 + 8 = 16 days, too long. It now splits both periods into 4 stages (Erlang stays)
  with a 7-day latent and 8-day infectious period: mean generation time 12.0 days
  (`simulator.generation_time`, tested against the 11 to 12 band in
  `tests/project/model/test_simulator.py`). The 7-day latent mean and the stage counts are a
  model choice to match that, so the latent period itself stays UNVERIFIED.
- R0: keep 12 to 18 as UNVERIFIED and treat it as too narrow (guerra2017) until the review's
  medians by setting are read.
