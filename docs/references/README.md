# References for model priors (B17, U12, U13)

Only citations, the figures used and short quotes locating them are kept here. Abstracts and
article text are not committed (I10). Records are fetched by the manual `references` workflow
(`measles references`) from Europe PMC; PubMed E-utilities is disallowed by NCBI's robots.txt
for this client and is not used (I7). Every reference is identified by its DOI, which
`references.yml` holds and the fetcher checks against the record returned; links below resolve
through doi.org.

| Key | Citation | DOI | What the source says (observed) | Status |
|---|---|---|---|---|
| klinkenberg2011 | Klinkenberg D, Nishiura H. The correlation between infectivity and incubation period of measles, estimated from households with two cases. J Theor Biol. 2011. PMID 21704640 | [10.1016/j.jtbi.2011.06.015](https://doi.org/10.1016/j.jtbi.2011.06.015) | Abstract: the mean incubation period and the generation time of measles "both lie in the range of 11-12 days". Introduction (owner-supplied text): estimates come from households and "cannot directly be extrapolated beyond the household setting"; with equally distributed incubation periods the mean generation time equals the mean serial interval | VERIFIED 2026-10-08 (run gh-37860465223); introduction read 2026-10-09 |
| guerra2017 | Guerra FM, Bolotin S, Lim G, Heffernan J, Deeks SL, Li Y, Crowcroft NS. The basic reproduction number (R0) of measles: a systematic review. Lancet Infect Dis. 2017;17:e420-e428. PMID 28757186 | [10.1016/S1473-3099(17)30307-9](https://doi.org/10.1016/S1473-3099(17)30307-9) | 18 studies, 58 estimates from 1.43 to 770.38; 10 within 12-18, 16 above, 27 below (p. e423). Table 2 medians (p. e426): Americas 15.3 (range 10.7-27.0; 3 publications, 4 estimates); developed countries, vaccine era 11.7 (6.2-32.1; 6, 10); outbreak data 9.9 (6.2-32.1; 4, 8); surveillance data 13.2; vaccine era overall 15.7; low density (<1000 per km2) 12.6; birth rate >20 per 1000 12.9. Table 1 (p. e422): Glasser et al. 2016, California 2008, school-specific next-generation matrices, 10.7 well mixed and 18.1 structured. Conclusion: "Context-specific estimates of R0 are needed" | VERIFIED 2026-10-09 from the full text (owner-supplied copy, not committed) |
| vink2014 | Vink MA, Bootsma MCJ, Wallinga J. Serial intervals of respiratory infectious diseases: a systematic review and analysis. Am J Epidemiol. 2014;180(9):865-875 | [10.1093/aje/kwu209](https://doi.org/10.1093/aje/kwu209) | Abstract: mean serial interval for measles "11.7 days". Full text (p. 870, Table 3): 6 usable household data sets give means between 9.9 and 13.8 days, pooled 11.7; the one US data set (Chapin 1925, Providence, 5,659 intervals) 11.9 (95% CI 11.8-12.0). Literature values 9 to 13 days (Table 2). The PMID first used (25262286) returned an unrelated paper, caught by the DOI check | VERIFIED 2026-10-08 (run gh-37861236213, DOI match); full text read 2026-10-09 (owner-supplied copy, not committed) |

## What this means for the model

- Generation time 11 to 12 days (klinkenberg2011), serial interval 11.7 days pooled, 9.9 to
  13.8 by data set, 11.9 in the one US data set (vink2014). These are household estimates
  (klinkenberg2011 cautions against extrapolating beyond households). The simulator's stays
  were geometric, giving a mean generation time of 8 + 8 = 16 days, too long. It now splits both
  periods into 4 stages (Erlang stays) with a 7-day latent and 8-day infectious period: mean
  generation time 12.0 days (`simulator.generation_time`, tested against the 11 to 12 band in
  `tests/project/model/test_simulator.py`). The 7-day latent mean and the stage counts are a
  model choice to match that, so the latent period itself stays UNVERIFIED.
- R0 (guerra2017): no single value is supported; the review asks for estimates from similar
  settings. The prior is 9.9 to 18.1 (ADR 0007): from the median of outbreak-data estimates
  (9.9) to the structured estimate for the one US school-outbreak study (Glasser et al. 2016,
  18.1). It contains the developed-country vaccine-era median (11.7), the Glasser well-mixed
  estimate (10.7) and the Americas median (15.3). Calibration (6c) narrows it; the prior is not
  a finding about Pennsylvania.

Article copies supplied by the owner are read in the session only. They are not committed and
their download stamps are not quoted (I10).
