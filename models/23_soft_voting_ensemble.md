# Soft-Voting Ensemble: XGBoost + HistGradientBoosting + L1 Logistic Regression

> **One-liner:** Average the calibrated probabilities of three architecturally different learners (a sparse linear model, two independent gradient-boosting implementations) and use the same three-model bakeoff to compare feature setups honestly.
> **Category:** method (tree + linear ensemble) ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial (the L1 logistic component is fully interpretable; the voted probability is not)

## Why it fits Genome Firewall
L1 logistic regression, XGBoost, and HistGradientBoosting make genuinely different errors on
this data: L1 LR is an additive linear model over sparse binary columns and will miss
gene×gene interactions; the two boosting libraries capture those interactions but use
different binning/regularization internals (XGBoost's exact/hist tree builder with
`reg_lambda`/`reg_alpha` vs sklearn's native histogram builder), so their mistakes are only
partially correlated. Averaging three diverse, individually-calibratable models is the
cheapest way to reduce variance on a small, imbalanced, per-antibiotic dataset **without**
the leakage surface of a fitted meta-learner (see [22](22_stacking_ensemble.md), which trains
a meta-model on out-of-fold predictions) — soft voting has no meta-learner to overfit, only
fixed or lightly-tuned weights. It also gives a natural, cheap way to answer a second
question this catalog cares about: **which feature setup actually helps**, since the same
three-model harness can be re-run unchanged on the presence/absence matrix alone, on any
embedding matrix alone, or on their concatenation, and compared head-to-head on identical
splits.

## When to prefer it / when to skip it
Prefer this over the general stacking file (22) when you want the robustness benefit of
combining models with the smallest possible leakage surface and near-zero tuning: soft
voting needs no out-of-fold meta-feature machinery. Prefer it over any single boosted-tree
file (08/09) when you have already confirmed the three base learners make sufficiently
uncorrelated errors (see the adversarial check below) — if they don't, the "ensemble" gain
is illusory and you should just report the best single model. **Skip it, or keep it
secondary, if it does not beat both the L1 logistic-regression component alone and the L2
baseline ([01](01_logistic_regression_l2.md)) on held-out test Brier** — three models are
three times the compute and interpretability cost of one, and that cost must be earned.
Whatever the voting result, **keep the L1 logistic regression's own coefficients as the
reported explainable artifact** (rule 5); the voted probability is a statistical blend, not
a causal explanation.

## Data interface (the contract this code must respect)
- Baseline features: `data/processed/features.parquet` (index `genome_id`, binary int8
  presence/absence of AMR genes + named point mutations).
- Optional embedding features, if already produced by another model file in this catalog —
  used only to build the alternate feature setups below, never to change the protocol:
  - ESM-2 per-genome embeddings from [17](17_esm2_embeddings_linear.md) /
    [18](18_esm2_finetune.md).
  - DNABERT-2 / Nucleotide Transformer / HyenaDNA per-genome embeddings from
    [19](19_nucleotide_transformer.md) / [24](24_hyenadna.md), if computed (the region prep
    for DNABERT-2 already exists locally: `data/interim/dnabert2_regions/`, produced by
    `scripts/prepare_dnabert2_regions.py`).
- `data/processed/labels.csv` — per antibiotic R/S label per `genome_id`.
- `data/processed/splits.json` — grouped `train`/`cal`/`test` + `cluster_id`.
- `db/drugs_saureus.csv` — target gate reference.
- **Feature setups to compare** (same three base learners, same splits, run once per
  setup):
  1. `genotype_only` — `features.parquet` alone.
  2. `embedding_only` — one embedding source alone (pick whichever is available; name it
     explicitly, e.g. `esm2_only` or `dnabert2_only`).
  3. `genotype_plus_embedding` — the two concatenated (e.g. `genotype_plus_esm2`).
  Every genome fed into a given setup must have every column that setup requires; drop or
  explicitly impute genomes missing an embedding rather than silently zero-filling.

## Adversarial checks it must survive
- **Leakage (Rule 1):** each base learner and the whole ensemble still obey `splits.json`
  verbatim; any internal validation (early stopping, voting-weight tuning) is carved from
  `train` via GroupKFold on `cluster_id` — never `cal`/`test`.
- **Voting-weight tuning is still a leakage vector:** if the voting weights (when not
  uniform) are chosen by looking at `cal` or `test` performance, that leaks exactly like
  meta-feature leakage does in stacking. Tune weights (uniform vs Brier-weighted vs a small
  grid) only via out-of-fold GroupKFold scoring **inside `train`**.
- **Illusory diversity:** if XGBoost and HistGradientBoosting agree on almost every genome
  because they are both trees fit on the same tiny sparse binary matrix, the ensemble is not
  actually diverse and the "gain" over the better single model may be noise. Before trusting
  the combination, report the pairwise disagreement rate / error correlation between the
  three base learners' train-GroupKFold out-of-fold predictions.
- **Calibration order matters (Rule 2):** "calibrate each base model, then average the
  calibrated probabilities" and "average raw scores, then calibrate once" are not
  equivalent and can produce different reliability curves — evaluate both on `test`, do not
  assume one is correct by default.
- **Clonal memorization / generalization (Rule 6):** the boosting components in particular
  can memorize *S. aureus* lineage structure; judge on the per-genetic-group breakdown
  including unseen clusters, and expect boosting-heavy setups to drop more there than the
  L1 LR component does.
- **Honest explanations (Rule 5):** only the L1 logistic regression's nonzero coefficients
  (cross-checked against `known_markers` in `drugs_saureus.csv`) are reportable as an
  explanation; XGBoost/HistGradientBoosting importances and the voted probability itself are
  statistical only. If an `embedding_only`/`genotype_plus_embedding` setup wins, say plainly
  that embeddings carry **no** gene-level causal attribution at all.
- **Honest feature-setup comparison:** run the identical grouped splits + identical
  calibration protocol for every feature setup, and report per-antibiotic results, not just
  an aggregate — a setup that wins on average by winning big on one easy antibiotic and
  losing narrowly on the rest is not an honest overall winner.
- **Target gate (Rule 4):** the ensemble's "S" must still clear the deterministic target
  gate; absence of markers alone never yields "likely to work."

## Hyperparameters worth sweeping
- **Voting weights:** uniform (1/3 each) vs a small Brier-weighted grid, selected via
  GroupKFold-on-`cluster_id` **inside train only**.
- **Calibration order:** calibrate-then-vote vs vote-then-calibrate; calibration method
  (Platt/sigmoid vs isotonic) given how small `cal` typically is.
- **L1 logistic regression:** `C` (logspace `1e-2…1e2`), `solver="saga"`/`liblinear`,
  `class_weight="balanced"`.
- **XGBoost:** `max_depth` (2–6), `eta` (0.01–0.3), `n_estimators` (100–1000, early-stopped
  on a `train`-derived GroupKFold set), `scale_pos_weight`, `reg_lambda`/`reg_alpha`.
- **HistGradientBoosting:** `learning_rate` (0.01–0.3), `max_iter`, `max_leaf_nodes`
  (7/15/31), `min_samples_leaf`, `l2_regularization`; `early_stopping` set explicitly to a
  `train`-derived GroupKFold set, never sklearn's default random split.
- **Feature setup:** `genotype_only` / `embedding_only` / `genotype_plus_embedding`, and
  which embedding source when more than one is available.

## Calibration & no-call handling
Fit all three base learners on `train` for a given feature setup (early stopping, if used,
drawn from a `train`-only GroupKFold split). Produce the ensemble probability either by
calibrating each base learner on `cal` first (via `CalibratedClassifierCV(cv="prefit")`)
and averaging the three calibrated probabilities, or by averaging the three raw
probabilities and calibrating that single averaged score on `cal` — run and report both.
Feed the resulting calibrated P(R) into the shared no-call logic: `no-call` when p falls in
the ambiguous band (~0.4–0.6), when the genome is out-of-distribution relative to `train`,
or when the target gate fires. Report reliability before and after calibration, for both
calibration orderings.

## Metrics to report
On the held-out grouped **test** split, and per genetic group (including unseen clusters):
balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability
diagram**, no-call rate + accuracy-on-called. Report every headline metric as a **delta
versus the L2 baseline (file 01) and versus the L1 logistic-regression component alone**,
so the ensemble's added compute is judged against both the project baseline and its own
best single ingredient. Build one leaderboard row per `(antibiotic, feature_setup,
calibration_order)` and sort by antibiotic then Brier ascending.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible), with a CALIBRATED confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, xgboost, pandas, numpy, matplotlib) that builds a SOFT-VOTING ENSEMBLE of exactly three base learners — (1) L1-penalized LogisticRegression, (2) XGBClassifier, (3) HistGradientBoostingClassifier — one ensemble PER antibiotic, and compares it across multiple FEATURE SETUPS.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- OPTIONAL embedding parquet(s), if present on disk (e.g. an ESM-2 or DNABERT-2 per-genome embedding matrix produced by another stage of this pipeline): one row per genome, index genome_id, float columns emb_0..emb_k. Treat as optional input — the script must run correctly on features.parquet alone if no embedding file is found, and must clearly report which genomes it had to drop or skip when an embedding is requested but missing.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

FEATURE SETUPS (make this a parameter, loop over all setups that are actually buildable from what's on disk):
1. genotype_only: features.parquet alone.
2. embedding_only: a single embedding matrix alone (name it after its source, e.g. esm2_only).
3. genotype_plus_embedding: the two concatenated on genome_id (inner join; report and log any genomes dropped).
Skip a setup cleanly (with a printed message) if its required input file is not present — do not fabricate it.

PROTOCOL (obey exactly), for every (antibiotic, feature_setup) pair:
1. Fit all three base learners on the TRAIN split ONLY. Map label R->1, S->0. Handle class imbalance with class_weight="balanced" (logistic regression) / scale_pos_weight (xgboost) / sample_weight (HistGradientBoosting). Do NOT use SMOTE or synthetic oversampling.
2. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json. If any base learner uses early stopping or internal validation, carve it from TRAIN via GroupKFold on cluster_id; HistGradientBoosting's default early_stopping uses a random split, so set it explicitly to a GroupKFold-derived set instead. Never touch cal or test for this.
3. Compute BOTH calibration orderings and report both: (a) calibrate each of the three base learners on the CAL split with CalibratedClassifierCV(cv="prefit") (try sigmoid and isotonic, keep the lower-Brier one per learner), then average the three calibrated probabilities; (b) average the three learners' raw probabilities first, then fit a single CalibratedClassifierCV-style calibration (sigmoid/isotonic) on that averaged score using the CAL split.
4. Voting weights default to uniform (1/3 each); also support a small weight grid (e.g. uniform vs Brier-inverse-weighted) selected ONLY via GroupKFold-on-cluster_id scoring inside TRAIN — never selected by looking at cal or test performance.
5. Report ALL metrics on the TEST split ONLY.
6. Before trusting the ensemble, compute the pairwise disagreement rate between the three base learners' TRAIN-GroupKFold out-of-fold predictions, and print it — this checks whether they are actually diverse or just three correlated trees/linear models.

HONESTY REQUIREMENT: also fit a standalone L1 logistic regression on genotype_only features and keep ITS nonzero coefficients as the EXPLAINABLE artifact (cross-reference against known_markers in drugs_saureus.csv, label nonzero coefficients as statistical associations for this dataset, not proven causation). Report every ensemble metric as a DELTA versus (a) the L2 baseline and (b) this L1 logistic-regression component alone. If an embedding-based feature setup wins, explicitly state it gives no gene-level causal attribution.

OUTPUT / METRICS:
- On the TEST split, and PER genetic group (cluster_id) including clusters unseen in training, compute for every (antibiotic, feature_setup, calibration_order) combination: n_train, n_cal, n_test, balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, no-call rate, and accuracy-on-called, where "no-call" = calibrated p in the ambiguous band ~0.4-0.6 (leave OOD and target-gate no-calls as stub hooks).
- Save one leaderboard CSV (e.g. reports/ensemble_model_comparison.csv) with one row per (antibiotic, feature_setup, calibration_order), sorted by antibiotic then Brier ascending then balanced accuracy descending. Print a compact rounded summary table.
- Plot a reliability diagram per antibiotic for the best-Brier (feature_setup, calibration_order) combination, and a grouped bar chart of Brier by antibiotic and feature_setup.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate data — if a required input file is missing, skip that feature setup and say so, don't invent one. Output clean, self-contained, reproducible (fixed random_state) Python in execution order.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
