# Random Forest (sklearn)

> **One-liner:** A bagged ensemble of decision trees that averages many bootstrapped, feature-subsampled trees to predict per-antibiotic resistance from a sparse binary AMR matrix.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial (Gini/permutation importances — statistical, not causal)

## Why it fits Genome Firewall
Our feature matrix is a wide, sparse block of binary AMR gene- and mutation-presence columns, and resistance is often driven by combinations (e.g. a target-site mutation plus an efflux gene) rather than any single marker. Random Forest natively captures these gene×gene interactions without hand-engineering them, tolerates the many all-zero columns that come from taking a union of markers across the dataset, and is robust on the small, imbalanced per-antibiotic label sets we have. Because the judged priority is calibration, RF's well-known tendency to be *under-confident* (probabilities pulled toward the class base rate by averaging) is a feature we can fix cleanly with isotonic calibration on the dedicated `cal` split.

## When to prefer it / when to skip it
Prefer RF as a strong, low-friction baseline when you want interaction-aware predictions with almost no tuning risk and no extra dependencies beyond scikit-learn. It is a good sanity check that the boosting models (HistGradientBoosting, XGBoost, LightGBM, CatBoost) are actually earning their extra complexity. Skip it, or treat it as secondary, when a well-tuned boosting model already dominates on the per-genetic-group breakdown and Brier score, or when you specifically need monotonic constraints or the leaf-wise efficiency of boosting on the larger antibiotic label sets. For a truly interpretable, causally-honest baseline, the L1/L2 logistic model is easier to read; RF importances only rank statistical association.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); all columns are int8 binary presence/absence of AMR gene symbols and named point mutations; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — columns `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — maps `genome_id` → `{"split": "train"|"cal"|"test", "cluster_id": int}`. Grouped by genetic cluster: no `cluster_id` spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one RF **per antibiotic**. Fit on `train` only, calibrate on `cal` only, report all metrics on `test` only. Never re-split randomly; if you need an internal validation set, carve it from `train` via GroupKFold on `cluster_id`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** *S. aureus* is clonal, so a high-capacity forest can effectively memorize lineage/clonal structure that co-occurs with resistance and look excellent on any within-lineage evaluation. The provided split is grouped by `cluster_id` precisely to break this — respect it, and judge the model on the **per-genetic-group breakdown, especially clusters unseen in training**, not on aggregate test accuracy. Any tuning that uses a validation set must draw it from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.
- **Poor / skewed calibration (rigor rule 2):** RF probabilities are averages of votes and are typically under-confident and step-shaped. Do not trust raw `predict_proba`; wrap in isotonic calibration fit on `cal`, then report Brier + reliability on `test`.
- **Importances are not causation (rigor rule 5):** Gini or permutation importances rank statistical association with the label; correlated markers and clonal confounding can inflate them. Label any importance-based explanation as statistical-only and cross-check named hits against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** A confident "S" driven purely by all-zero markers must still pass the deterministic target gate before it can become "likely to work."
- **Imbalance:** use `class_weight="balanced"` or `"balanced_subsample"` rather than resampling; do not use SMOTE across the grouped structure.

## Hyperparameters worth sweeping
- `n_estimators`: 300–1000 (more trees stabilize probabilities, which helps calibration; cost is CPU only).
- `max_depth`: None vs a cap of 4–16 — capping directly fights clonal memorization on unseen clusters.
- `min_samples_leaf`: 1, 2, 5, 10 — larger leaves smooth probabilities and reduce overfit on tiny classes.
- `max_features`: "sqrt", "log2", or a small fraction (0.1–0.3) — low values suit the sparse binary matrix.
- `class_weight`: "balanced" vs "balanced_subsample".
- `min_samples_split`, `max_samples` (bootstrap fraction) for additional regularization.
Select over these using GroupKFold on `cluster_id` **within train**, scoring on Brier and balanced accuracy.

## Calibration & no-call handling
Fit the RF on `train`, then wrap the fitted estimator with `CalibratedClassifierCV(..., method="isotonic", cv="prefit")` fit on the `cal` split (isotonic is preferred here because RF is under-confident and monotone-miscalibrated, and `cal` gives a dedicated held-out set). Use the calibrated probability of `R` as the score. Feed that calibrated p into the shared no-call logic: return `no-call` when p sits in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution (e.g. its markers are unlike anything in train, or it belongs to an unseen cluster with low support), or when the target gate fires. Report the reliability diagram before and after calibration to show the correction.

## Metrics to report
On the held-out grouped `test` split, and broken down per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Expect and report a performance drop on unseen clusters. Save a per-antibiotic metrics dict to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python (scikit-learn) that trains a RANDOM FOREST classifier, one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training so generalization is reported honestly.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one Random Forest per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you need an internal validation set for hyperparameter selection, carve it from TRAIN using GroupKFold on cluster_id; never touch cal or test.
- Handle class imbalance with class_weight="balanced" or "balanced_subsample". Do NOT use SMOTE/synthetic oversampling.
- Random Forest probabilities are typically UNDER-confident, so calibrate: wrap the fitted forest in CalibratedClassifierCV(method="isotonic", cv="prefit") fit on the cal split. Use the calibrated probability of R as the score.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): n_estimators (300-1000), max_depth (None or 4-16), min_samples_leaf (1,2,5,10), max_features ("sqrt","log2",0.1-0.3), class_weight ("balanced" vs "balanced_subsample").

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the calibrated probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. Plot reliability diagrams before vs after calibration.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a tree ensemble memorize lineage structure, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_state) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
