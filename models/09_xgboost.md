# XGBoost

> **One-liner:** A regularized gradient-boosted tree library and one of the strongest general tabular performers, with `scale_pos_weight` for imbalance and SHAP for (statistical-only) explanations.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU (optional GPU) ·
> **Priority:** recommended ·
> **Interpretable:** partial (SHAP available — statistical, not causal)

## Why it fits Genome Firewall
XGBoost is a consistently strong performer on exactly the kind of small, wide, sparse binary tabular matrix we have, and its L1/L2 regularization helps control overfitting when most of the AMR columns are near-empty. It models the marker interactions (target-site mutation plus efflux or modifying enzyme) that determine per-antibiotic R/S, has first-class handling of class imbalance via `scale_pos_weight`, and exposes SHAP values for per-prediction explanation. Because it is high-capacity boosting and calibration is the judged priority, we never present raw margins as probabilities — we calibrate on `cal` and report Brier + reliability on `test`.

## When to prefer it / when to skip it
Prefer XGBoost when you want a battle-tested boosting model with mature SHAP explanations and an optional GPU path for wider sweeps, and when you are willing to tune it carefully. It is a natural top-tier candidate alongside LightGBM and CatBoost. Skip it, or deprioritize, when you want zero install friction (use HistGradientBoosting), when the dataset is small enough that CatBoost's ordered boosting is safer against overfit, or when LightGBM's leaf-wise speed matters more — and always confirm XGBoost actually beats those on the per-genetic-group Brier before accepting its tuning burden.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); int8 binary presence/absence columns; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — `genome_id` → `{"split", "cluster_id"}`; grouped by genetic cluster, no cluster spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one booster **per antibiotic**. Fit on `train`, calibrate on `cal`, report metrics on `test`. Early-stopping validation must be carved from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** XGBoost is high-capacity and, on a clonal organism like *S. aureus*, can memorize lineage/clonal structure that correlates with resistance — looking great on internal validation but failing on new lineages. The grouped `cluster_id` split breaks this: judge on the **per-genetic-group breakdown, especially unseen clusters**, and on Brier, not aggregate accuracy. The single most common leak here is early stopping on a randomly held-out validation set — the eval set MUST be carved from `train` via GroupKFold on `cluster_id`, never from `cal`/`test` and never a random split, so no cluster spans train and eval.
- **Poor / skewed calibration (rigor rule 2):** boosted-tree probabilities are often over- or mis-confident; apply isotonic or Platt calibration on `cal` and report Brier + reliability on `test`.
- **SHAP is not causation (rigor rule 5):** SHAP explains the model's use of a feature, not biological causation; correlated markers and clonal confounding move SHAP too. Label SHAP explanations statistical-only and cross-check named markers against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** a confident "S" from all-zero markers must clear the deterministic target gate before becoming "likely to work."
- **Imbalance:** set `scale_pos_weight` to the neg/pos ratio per antibiotic; do not use SMOTE across the grouped structure.

## Hyperparameters worth sweeping
- `max_depth`: 2–6 (shallow trees resist clonal memorization).
- `eta` (learning_rate): 0.01–0.3.
- `n_estimators` / num_boost_round: 100–1000 with early stopping on a GroupKFold-from-train eval set.
- `subsample`: 0.5–1.0; `colsample_bytree`: 0.3–1.0 (lower suits the sparse matrix).
- `min_child_weight`: 1–20 (higher regularizes tiny classes).
- `reg_lambda`, `reg_alpha`: 0–10 (L2/L1).
- `scale_pos_weight`: neg/pos ratio.
Select with GroupKFold on `cluster_id` **within train**, scoring Brier and balanced accuracy.

## Calibration & no-call handling
Fit the booster on `train` with early stopping on a `train`-derived GroupKFold eval set, then wrap the fitted model in `CalibratedClassifierCV(..., cv="prefit")` on `cal` — try both `method="isotonic"` and `method="sigmoid"`, keep the lower-Brier one. Use calibrated P(R) as the score and feed it to the shared no-call logic: `no-call` when calibrated p is in ~0.4–0.6, when the genome is out-of-distribution, or when the target gate fires. Show reliability before and after calibration.

## Metrics to report
On the held-out grouped `test` split and per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report the expected drop on unseen clusters. Save per-antibiotic metrics to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python using XGBoost (xgboost) that trains a gradient-boosted tree classifier, one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training so generalization is reported honestly.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one XGBoost model per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you use early stopping (recommended), the eval/validation set MUST be carved from TRAIN using GroupKFold on cluster_id — never a random split, and never cal or test — so no cluster spans train and eval.
- Handle class imbalance with scale_pos_weight set to the neg/pos ratio per antibiotic. Do NOT use SMOTE/synthetic oversampling.
- Boosted-tree probabilities are often over-confident, so calibrate: wrap the fitted model in CalibratedClassifierCV(cv="prefit") fit on the cal split; try method="isotonic" and method="sigmoid" and keep the lower-Brier one. Use the calibrated probability of R as the score.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): max_depth (2-6), eta/learning_rate (0.01-0.3), n_estimators/num_boost_round (100-1000 with early stopping), subsample (0.5-1.0), colsample_bytree (0.3-1.0), min_child_weight (1-20), reg_lambda and reg_alpha (0-10), scale_pos_weight (neg/pos ratio).

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the calibrated probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. Plot reliability diagrams before vs after calibration. You may compute SHAP values for explanation, but clearly label them as STATISTICAL association, NOT biological causation.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a boosted-tree model memorize lineage structure, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_state) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
