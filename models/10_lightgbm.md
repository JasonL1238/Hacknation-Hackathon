# LightGBM

> **One-liner:** A fast, leaf-wise gradient-boosting library that handles sparse features efficiently and offers `is_unbalance`/`scale_pos_weight` for imbalanced per-antibiotic labels.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU (optional GPU) ·
> **Priority:** recommended ·
> **Interpretable:** partial (gain importance / SHAP — statistical, not causal)

## Why it fits Genome Firewall
LightGBM grows trees leaf-wise and bins features, which makes it fast and memory-light on our wide, sparse binary AMR matrix and lets us sweep many configs on CPU. It captures the marker interactions behind per-antibiotic R/S and has direct imbalance handling via `is_unbalance` or `scale_pos_weight`. Its main risk on our small data is that leaf-wise growth overfits aggressively, so — with calibration as the judged priority — we constrain complexity, calibrate on `cal`, and report Brier + reliability on `test` rather than trusting raw probabilities.

## When to prefer it / when to skip it
Prefer LightGBM when speed matters — many antibiotics, wide sweeps, or an optional GPU — and when the sparse feature handling gives it an edge. It sits alongside XGBoost and CatBoost as a top-tier boosting candidate. Skip it, or tune it very conservatively, when the per-antibiotic label sets are small enough that leaf-wise growth overfits despite regularization (CatBoost's ordered boosting is safer there), or when you want zero install friction (HistGradientBoosting). Always confirm it beats the alternatives on the per-genetic-group Brier, not just aggregate AUROC.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); int8 binary presence/absence columns; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — `genome_id` → `{"split", "cluster_id"}`; grouped by genetic cluster, no cluster spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one booster **per antibiotic**. Fit on `train`, calibrate on `cal`, report metrics on `test`. Early-stopping validation must be carved from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** leaf-wise boosting is especially prone to fitting fine structure, so on a clonal organism like *S. aureus* LightGBM can memorize lineage/clonal patterns that co-occur with resistance and look great on internal validation while failing on new lineages. The grouped `cluster_id` split breaks this — judge on the **per-genetic-group breakdown, especially unseen clusters**, and on Brier, not aggregate accuracy. Any `early_stopping` validation set MUST be carved from `train` via GroupKFold on `cluster_id`, never a random split and never from `cal`/`test`, so no cluster spans train and eval.
- **Leaf-wise overfit on small data:** cap `num_leaves`, raise `min_child_samples`, and use bagging/feature fractions and L1/L2 — otherwise a few deep leaves memorize individual genomes.
- **Poor / skewed calibration (rigor rule 2):** boosted-tree probabilities are often mis-confident; apply isotonic or Platt calibration on `cal` and report Brier + reliability on `test`.
- **Importance / SHAP is not causation (rigor rule 5):** gain importance and SHAP reflect model use of a feature under clonal confounding, not biological causation — label them statistical-only and cross-check named markers against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** a confident "S" from all-zero markers must clear the deterministic target gate.
- **Imbalance:** use `is_unbalance=True` or `scale_pos_weight`; do not use SMOTE across the grouped structure.

## Hyperparameters worth sweeping
- `num_leaves`: 7, 15, 31 (keep small on this data to avoid leaf-wise overfit).
- `learning_rate`: 0.01–0.3.
- `n_estimators`: 100–1000 with early stopping on a GroupKFold-from-train eval set.
- `min_child_samples`: 10–50 (higher regularizes tiny classes).
- `feature_fraction`: 0.3–1.0; `bagging_fraction`: 0.5–1.0 (with `bagging_freq`).
- `lambda_l1`, `lambda_l2`: 0–10.
- `max_depth`: -1 or a 3–8 cap paired with small `num_leaves`.
- `is_unbalance` vs explicit `scale_pos_weight`.
Select with GroupKFold on `cluster_id` **within train**, scoring Brier and balanced accuracy.

## Calibration & no-call handling
Fit on `train` with early stopping on a `train`-derived GroupKFold eval set, then wrap the fitted model in `CalibratedClassifierCV(..., cv="prefit")` on `cal` — try both `method="isotonic"` and `method="sigmoid"`, keep the lower-Brier one. Use calibrated P(R) as the score and feed it to the shared no-call logic: `no-call` when calibrated p is in ~0.4–0.6, when the genome is out-of-distribution, or when the target gate fires. Show reliability before and after calibration.

## Metrics to report
On the held-out grouped `test` split and per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report the expected drop on unseen clusters. Save per-antibiotic metrics to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python using LightGBM (lightgbm) that trains a gradient-boosted tree classifier, one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training so generalization is reported honestly.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one LightGBM model per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you use early stopping (recommended), the eval/validation set MUST be carved from TRAIN using GroupKFold on cluster_id — never a random split, and never cal or test — so no cluster spans train and eval.
- Handle class imbalance with is_unbalance=True or scale_pos_weight (neg/pos ratio). Do NOT use SMOTE/synthetic oversampling.
- LightGBM grows leaf-wise and OVERFITS easily on small data, so constrain complexity (small num_leaves, higher min_child_samples, bagging/feature fractions, L1/L2). Boosted-tree probabilities are often mis-confident, so calibrate: wrap the fitted model in CalibratedClassifierCV(cv="prefit") fit on the cal split; try method="isotonic" and method="sigmoid" and keep the lower-Brier one. Use the calibrated probability of R as the score.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): num_leaves (7,15,31), learning_rate (0.01-0.3), n_estimators (100-1000 with early stopping), min_child_samples (10-50), feature_fraction (0.3-1.0), bagging_fraction (0.5-1.0 with bagging_freq), lambda_l1 and lambda_l2 (0-10), max_depth (-1 or 3-8), is_unbalance vs scale_pos_weight.

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the calibrated probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. Plot reliability diagrams before vs after calibration. You may compute SHAP/gain importance for explanation, but clearly label it as STATISTICAL association, NOT biological causation.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a leaf-wise boosted model memorize lineage structure, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_state) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
