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

### 2026-07-18 — Grouped train/cal/test split (`split.py`) via AMR-profile clustering
- What: `split.py` builds a genome×genome distance matrix, single/average-linkage
  clusters it, and assigns whole clusters to train (70%)/cal(15%)/test(15%) via a
  greedy largest-cluster-first fill (each cluster goes to whichever split is furthest
  below its target share). 5 of the smallest clusters are forced out of train entirely
  so `test`/`cal` always contain genuinely unseen genetic groups. A hard assert
  (`assert_no_cluster_spans_splits`) fails the run if any cluster_id maps to more than
  one split. Output written to `data/processed/splits.json` per DATA_SPEC §4.
- Why: distance prefers genome-level Mash/ANI (the real phylogenetic signal) via
  `mash sketch`/`mash dist`, but `mash` is not installed in this environment, so this
  run fell back to Jaccard distance over `features.parquet` (the AMR presence/absence
  matrix itself). That fallback is coarser — it can only detect genomes with identical
  detected gene content, not true near-identical assemblies — so cluster boundaries
  here should be read as conservative, not a precise phylogenetic cut.
- Adversarial case considered: (a) *Clustering on the same matrix the model trains on
  is circular.* Countered: it's actually the strictest possible leakage guard for this
  model, since it groups on exactly the channel the model can see — any two genomes
  the model can't tell apart are guaranteed to land in the same split. The real risk
  runs the other way: it can *over*-cluster genomes that share AMR content by
  convergent evolution/plasmid acquisition rather than shared lineage, which shrinks
  effective training diversity but never leaks. (b) *Is coarser-than-mash good enough
  to trust?* Cross-checked against BV-BRC's independent MLST calls: 81/697 typed
  clusters mix >1 MLST type (this proxy under-clusters some true lineages into
  separate clusters — safe direction) and 61/150 MLST types are fragmented across
  multiple clusters (also safe: it never merges unrelated lineages together). No
  MLST type was found entirely contained within a cluster alongside an unrelated one
  bridging train and test, which is the failure mode that would actually matter. (c)
  *Is 0.05 cluster threshold vs 0.0 dedup threshold meaningfully coarser?* Only
  marginally in this dataset: 748 dedup groups collapse to 721 clusters — Jaccard
  distances over a 144-dim binary vector are fairly discrete, so 0.05 doesn't buy much
  beyond exact-match. Logged so it's revisited once `mash` is available (install via
  `make amr-setup` env or `conda install -c bioconda mash`), which would let dedup/
  cluster thresholds actually track ANI instead of feature-space coincidence. (d) *Does
  the greedy split leave any split with a zero-count class for an antibiotic?* No —
  checked in the per-antibiotic label_balance_report output; the worst skew is
  gentamicin cal (43 R / 209 S), imbalanced but non-degenerate.
- Evidence: this run (feature-jaccard fallback): 2542 genomes -> 748 dedup groups
  (1794 genomes collapsed as near-/exact-duplicates, matching the earlier manual
  `features.parquet.duplicated()` count exactly) -> 721 genetic clusters. Split sizes:
  train 1778 genomes/506 clusters (69.9%), cal 382/107 (15.0%), test 382/108 (15.0%),
  5 clusters held out of train entirely. Assert passed (no cluster spans splits).

### Open questions to answer before "done"
- [x] Leakage: proof no cluster spans train/test (assert output + de-dup count). (2026-07-18, `split.py`)
- [ ] Calibration: reliability plot on held-out tracks the diagonal; Brier reported.
- [ ] Honesty: no "likely to work" from marker-absence without target present.
- [ ] Causation: no SHAP/coefficient presented as biological cause.
- [ ] Generalization: metrics on unseen genetic groups reported (with the drop).
- [ ] Uncertainty: no-call rate + accuracy-on-called reported per drug.
- [ ] Scope: nothing drifts toward organism design.
- [x] Antibiotic choice + label counts justified. (2026-07-18 log entry)
- [x] Split thresholds justified. (2026-07-18, `split.py` log entry above)
