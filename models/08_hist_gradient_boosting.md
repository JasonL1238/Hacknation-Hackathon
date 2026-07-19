# HistGradientBoostingClassifier (sklearn, native)

## Current status and duplicate policy

This model is already implemented and tested in `genome_firewall.model_ensemble`. It uses
the committed Mash split, grouped train-only tuning, and normalized inverse labeled
`dedup_group_id` weights. Retain it as a nonlinear reference; do not retune from test.

> **One-liner:** scikit-learn's built-in histogram-based gradient boosting — fast, dependency-free boosted trees with native early stopping and monotonic constraints.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial (permutation importance / partial dependence — statistical, not causal)

## Why it fits Genome Firewall
HistGradientBoosting bins features and grows boosted trees efficiently, which suits our sparse binary AMR matrix and captures the marker combinations (target mutation + efflux/enzyme gene) that drive resistance. It ships inside scikit-learn, so there is zero install friction on any teammate's machine, and it supports early stopping plus monotonic constraints — useful if we want to encode "presence of a known resistance marker should not decrease P(R)" in a defensible, non-causal-overclaiming way. As a boosting method its raw probabilities can be over- or mis-confident, so we calibrate on `cal` because calibration is the judged priority.

## When to prefer it / when to skip it
Retain HistGradientBoosting as the dependency-light nonlinear reference beside XGBoost.
Do not expand into more nearly identical tree libraries unless a new scientific question
requires it. Prefer the simpler calibrated model whenever its grouped performance is tied.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); int8 binary presence/absence columns; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — `genome_id` → split, `cluster_id`, and `dedup_group_id`; neither group type spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one model **per antibiotic**. Fit on `train`, calibrate on `cal`, report metrics on `test`. Early stopping / tuning validation must be carved from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** boosting is high-capacity and can memorize the lineage/clonal structure of a clonal organism like *S. aureus*, scoring beautifully on internal validation while failing on new lineages. The grouped `cluster_id` split breaks this — judge the model on the **per-genetic-group breakdown, especially unseen clusters**, and on Brier, not aggregate accuracy. Critically, HistGradientBoosting's built-in `early_stopping` will by default hold out a *random* validation fraction, which would let a cluster span train/validation; disable that and instead pass a validation set carved from `train` via GroupKFold on `cluster_id`.
- **Poor / skewed calibration (rigor rule 2):** boosted-tree probabilities are often mis-confident; apply isotonic or Platt calibration fit on `cal` and report Brier + reliability on `test`.
- **Importances are not causation (rigor rule 5):** use permutation importance / partial dependence for explanation, label it statistical-only, and cross-check named markers against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** a confident "S" from all-zero markers must clear the deterministic target gate before becoming "likely to work."
- **Imbalance and duplicates:** combine balanced class handling with normalized inverse labeled dedup-family sample weights; do not use SMOTE.

## Hyperparameters worth sweeping
- `learning_rate`: 0.01–0.3 (lower + more iterations usually calibrates better).
- `max_iter`: 100–1000 with early stopping on a GroupKFold-from-train validation set.
- `max_leaf_nodes`: 7, 15, 31 (small trees fight clonal memorization).
- `max_depth`: None vs 3–8.
- `min_samples_leaf`: 10–50 (higher smooths probabilities on tiny classes).
- `l2_regularization`: 0, 0.1, 1, 10.
- Optionally `monotonic_cst` to force known-marker presence to be non-decreasing in P(R).
Select with GroupKFold on `cluster_id` **within train**, scoring Brier and balanced accuracy.

## Calibration & no-call handling
Fit on `train` (with early stopping validation drawn from `train` via GroupKFold, `early_stopping` set explicitly rather than "auto" random split), then wrap the fitted model in `CalibratedClassifierCV(..., cv="prefit")` on `cal` — try both `method="isotonic"` and `method="sigmoid"` and keep whichever gives the lower Brier on a train-derived GroupKFold check. Use calibrated P(R) as the score. Feed it into the shared no-call logic: `no-call` when calibrated p is in ~0.4–0.6, when the genome is out-of-distribution, or when the target gate fires. Show reliability before and after calibration.

## Metrics to report
On the held-out grouped `test` split and per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report the expected drop on unseen clusters. Save per-antibiotic metrics to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python (scikit-learn) that trains a HistGradientBoostingClassifier (sklearn's native histogram-based gradient boosting), one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int, "dedup_group_id": int, "dedup_group_size": int}. Neither a cluster nor duplicate family spans splits.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one HistGradientBoostingClassifier per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. IMPORTANT: HistGradientBoosting's built-in early_stopping defaults to a RANDOM validation fraction, which would let a cluster span train/validation — do NOT use that. Instead, if you use early stopping or select hyperparameters, carve the validation set from TRAIN using GroupKFold on cluster_id and pass it explicitly; never touch cal or test.
- Handle class imbalance with class_weight="balanced" and pass normalized sample_weight = 1 / labeled dedup-group size in every fit and calibration step. Use duplicate weights for weighted metrics. Do NOT use SMOTE/synthetic oversampling.
- Boosted-tree probabilities are often mis-confident, so calibrate: wrap the fitted model in CalibratedClassifierCV(cv="prefit") fit on the cal split; try method="isotonic" and method="sigmoid" and keep the lower-Brier one. Use the calibrated probability of R as the score.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): learning_rate (0.01-0.3), max_iter (100-1000 with early stopping), max_leaf_nodes (7,15,31), max_depth (None or 3-8), min_samples_leaf (10-50), l2_regularization (0,0.1,1,10). Optionally use monotonic_cst so presence of a known resistance marker cannot decrease P(R).

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the calibrated probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. Plot reliability diagrams before vs after calibration.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a boosted-tree model memorize lineage structure, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_state) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
