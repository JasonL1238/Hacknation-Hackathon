# DECISIONS.md — decisions + self-questioning log

At every milestone, run the 7-question checklist (CLAUDE.md) and log answers + evidence
here. Also record every non-obvious modeling/data choice with its rationale, as you make
it — per CLAUDE.md's adversarial-by-default rule, include the strongest case against the
decision and why it doesn't hold.

## Template
```
### <date> — <decision or question>
- What: ...
- Why: ...
- Adversarial case considered: ... (the strongest argument this is wrong)
- Evidence: ... (numbers, plots, asserts)
```

## Log

### 2026-07-18 — Antibiotic shortlist (6 drugs) chosen by clean-label coverage
- What: selected `ciprofloxacin, gentamicin, tetracycline, erythromycin, cefoxitin,
  clindamycin` as the prediction targets. Selection is data-driven in
  `acquire.select_antibiotics`: rank BV-BRC lab-measured labels per antibiotic, require
  min(#R, #S) ≥ 200 so each drug can support a grouped train/cal/test split with a
  held-out class, drop mechanistically-redundant duplicates, take top-6 by total count.
- Why: these six have both the highest clean-label counts and strong, catalogued
  genotype→phenotype links in *S. aureus* (fluoroquinolone gyrA/grlA point mutations;
  aminoglycoside-modifying enzymes; tet efflux/ribosomal-protection; erm macrolide/
  lincosamide resistance; mecA/mecC → cefoxitin). Post-quality-filter min-class counts:
  cipro R1141/S1116, gent R357/S1636, tet R452/S1548, ery R1178/S860, cefox R1287/S524,
  clinda R732/S571.
- Adversarial case considered: (a) *Why cefoxitin and not oxacillin/methicillin?* All
  three read out the same mecA/mecC β-lactam-resistance mechanism; keeping more than one
  would double-count a single biological signal as separate targets and inflate apparent
  drug coverage. Cefoxitin has the best coverage of the three (1811 clean labels vs
  oxacillin 1519, methicillin 455) and is the current CLSI-preferred surrogate (more
  sensitive for heteroresistant/mecC strains), so it is the sole mecA entry;
  oxacillin/methicillin are hard-excluded in `REDUNDANT_ANTIBIOTICS`. (b) *Why drop
  linezolid/vancomycin/rifampin/daptomycin despite ~1200-1700 total labels?* Their
  min-class count is tiny (linezolid R6, vancomycin R51, rifampin R42, daptomycin R80) —
  resistance is genuinely rare, so a grouped split cannot put resistant isolates in all
  of train/cal/test. Predicting these honestly would be near-constant "S"; excluding
  them is the honest call, not a coverage loss. (c) *Is the ≥200 threshold arbitrary?*
  It is a judgment call, but it is the natural gap in this dataset — the 6 kept drugs all
  have min-class ≥ 524 except clindamycin (571) and gentamicin (357); the next candidate
  (trimethoprim/sulfamethoxazole) drops to 264 R and the ones after fall off a cliff
  (<130). Threshold is logged here so it can be revisited if the model needs it.
- Evidence: full 42-row ranking table printed by `acquire.run()` /
  `select_antibiotics`; reproduced from the filter funnel
  `all=51209 → S.aureus=46643 → measured-method=30515 → clean-phenotype=26790
  → good-quality=26738`.

### 2026-07-18 — Intermediate ("I") → R mapping
- What: SIR→binary rule in `labels.py` maps Resistant→R, Intermediate→R, Susceptible→S.
- Why: patient-safety conservative default — reporting an intermediate isolate as
  "likely to work" (S) is the dangerous error; folding I into R avoids it. Matches
  `config/saureus.yaml labels.intermediate_rule: R`. "I" is also rare in this data
  (519 rows dataset-wide, mostly outside the shortlist), so the choice moves few labels.
- Adversarial case considered: merging I→R could slightly inflate the resistant class
  and hurt calibration near the decision boundary. Mitigations/next steps: I-count is
  small so the effect is bounded; Stage 3 should run a sensitivity check (drop-I vs
  merge-I) and report whether balanced accuracy / Brier shift materially. Logged as an
  open item rather than assumed harmless.
- Evidence: `Resistant Phenotype` value counts — Susceptible 31948, Resistant 13077,
  Intermediate 519, (NaN 5647 and Nonsusceptible 18 are both excluded upstream).

### 2026-07-18 — "Measured-only" label filter (excluding predicted phenotypes)
- What: kept only AMR rows whose `Laboratory Typing Method` ∈ {Broth dilution, Disk
  diffusion, Agar dilution, MIC, Biofosun Gram-positive panels broth dilution} with a
  clean SIR `Resistant Phenotype`; dropped the 16985 rows with no typing method.
- Why: challenge rule requires lab-measured AST, not computationally-predicted
  phenotype. In this BV-BRC pull the `Evidence` column is uniformly "Laboratory Method",
  so the presence of a real typing method (not a `Computational Method`) is the
  discriminator; rows with a blank method are the untrustworthy ones and are excluded.
- Adversarial case considered: could a "Laboratory Method"-tagged row still be
  predicted? The typing-method whitelist guards against this — every kept row names a
  concrete wet-lab assay. Rows only carrying a `Computational Method` value never enter
  because they lack a measured `Laboratory Typing Method`. No MIC→breakpoint conversion
  was needed: every surviving row (including the 695 MIC-typed ones) already carries a
  BV-BRC-assigned categorical SIR call, so `labels.py` has no breakpoint table.
- Evidence: `Laboratory Typing Method` value counts (NaN 16985 dropped); MIC-method
  rows within the shortlist = 0 missing phenotype.

### 2026-07-18 — Drug→target/marker DB (`db/drugs_saureus.csv`) sourced from catalogs
- What: hand-curated one row per chosen antibiotic with drug_class, `target_genes`
  (molecular target for the Stage 2 target-gate), `known_markers` (catalogued resistance
  determinants), standardized_name.
- Why: the target gate and evidence-category (i) logic need a curated map; this is
  domain knowledge (pharmacology/microbiology), not experimental data, so authoring it
  directly does not violate the no-synthetic-data rule — but it must be auditable.
- Adversarial case considered: hand-curated content can be wrong or stale. Sources for
  each row: NCBI AMRFinderPlus reference gene catalog (gene symbols/marker naming so the
  strings line up with what `featurize.py` will emit), CARD, and CLSI/EUCAST for
  drug-class/target biology (e.g. cefoxitin as the mecA surrogate; gyrA/grlA QRDR targets
  for fluoroquinolones; 23S rRNA/rplV/rplD ribosomal targets for macrolide-lincosamide).
  Marker symbols were reconciled against real AMRFinderPlus v4.2.7 output (db
  2026-05-15.1) on a cipro/mecA-resistant genome: the DB now uses AMRFinderPlus's
  canonical `Element symbol` naming (`erm(C)` not `ermC`, `parC_S80F` not `grlA_S80F`,
  `tet(38)`, `aac(6')-Ie/aph(2'')-Ia`, `mecA`) so Stage 3's evidence-(i)/marker matching
  can string-compare against feature columns directly. `target_genes` (gyrA/parC/rplV/
  rplD/pbpA etc.) are essential/intrinsic genes AMRFinderPlus does not emit as features;
  Stage 3's target gate treats them as intrinsically present (per PLAN.md) — that gate's
  job is to block "works" from marker-absence, not to detect the target in the matrix.
- Evidence: `db/drugs_saureus.csv` validates against DATA_SPEC §5 (5 columns,
  `;`-separated gene lists).

### Open questions to answer before "done"
- [ ] Leakage: proof no cluster spans train/test (assert output + de-dup count).
- [ ] Calibration: reliability plot on held-out tracks the diagonal; Brier reported.
- [ ] Honesty: no "likely to work" from marker-absence without target present.
- [ ] Causation: no SHAP/coefficient presented as biological cause.
- [ ] Generalization: metrics on unseen genetic groups reported (with the drop).
- [ ] Uncertainty: no-call rate + accuracy-on-called reported per drug.
- [ ] Scope: nothing drifts toward organism design.
- [x] Antibiotic choice + label counts justified. (2026-07-18 log entry)
- [ ] Split thresholds justified.
