# CatBoost

> **One-liner:** A gradient-boosting library whose ordered boosting reduces overfit on small data and often yields comparatively well-calibrated probabilities out of the box.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU (optional GPU) ·
> **Priority:** recommended ·
> **Interpretable:** partial (feature importance / SHAP — statistical, not causal)

## Why it fits Genome Firewall
CatBoost's ordered boosting is designed to reduce the target-leakage-style overfit that plagues boosting on small datasets — exactly our situation with small, imbalanced per-antibiotic label sets over a wide sparse binary AMR matrix. It captures marker interactions behind R/S, offers `auto_class_weights="Balanced"` for imbalance, and its probabilities are often closer to calibrated than other boosters out of the box. That said, "often well-calibrated" is not a free pass: since calibration is the judged priority, we still verify on `cal`/`test` and calibrate if the reliability diagram or Brier says so.

## When to prefer it / when to skip it
Prefer CatBoost when the per-antibiotic data is small and you want the strongest built-in defense against boosting overfit, and when you value probabilities that are closer to calibrated before any post-hoc correction. It is a top-tier candidate alongside XGBoost and LightGBM. Skip it, or deprioritize, when install/build friction is a concern (HistGradientBoosting is dependency-free), or when LightGBM's leaf-wise speed is decisive for very wide sweeps. As always, decide on the per-genetic-group Brier, not aggregate accuracy.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); int8 binary presence/absence columns; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — `genome_id` → `{"split", "cluster_id"}`; grouped by genetic cluster, no cluster spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one model **per antibiotic**. Fit on `train`, calibrate on `cal` (if needed), report metrics on `test`. Early-stopping/eval validation must be carved from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** ordered boosting reduces overfit but does not immunize against memorizing lineage/clonal structure in a clonal organism like *S. aureus*; the model can still exploit lineage signal that co-occurs with resistance and look great on internal validation while failing on new lineages. The grouped `cluster_id` split breaks this — judge on the **per-genetic-group breakdown, especially unseen clusters**, and on Brier, not aggregate accuracy. Any `eval_set` used for early stopping MUST be carved from `train` via GroupKFold on `cluster_id`, never a random split and never `cal`/`test`, so no cluster spans train and eval.
- **"Well-calibrated by default" complacency (rigor rule 2):** do not assume CatBoost is calibrated — verify the reliability diagram and Brier on `test`, and if it is off, apply isotonic/Platt on `cal`. Report before/after either way.
- **Importance / SHAP is not causation (rigor rule 5):** CatBoost importances and SHAP reflect model use under clonal confounding, not biological causation — label statistical-only and cross-check named markers against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** a confident "S" from all-zero markers must clear the deterministic target gate before becoming "likely to work."
- **Imbalance:** use `auto_class_weights="Balanced"` (or explicit `class_weights`); do not use SMOTE across the grouped structure.

## Hyperparameters worth sweeping
- `depth`: 4–8 (shallower resists clonal memorization).
- `learning_rate`: 0.01–0.3.
- `iterations`: 200–2000 with `od_type`/`od_wait` early stopping on a GroupKFold-from-train eval set.
- `l2_leaf_reg`: 1–10.
- `auto_class_weights`: "Balanced".
- Optionally `random_strength` and `bagging_temperature` for extra regularization.
Select with GroupKFold on `cluster_id` **within train**, scoring Brier and balanced accuracy.

## Calibration & no-call handling
Fit on `train` with early stopping on a `train`-derived GroupKFold eval set. First check raw calibration on `cal`/`test`; if the reliability diagram or Brier is off, wrap the fitted model in `CalibratedClassifierCV(..., cv="prefit")` on `cal` — try `method="isotonic"` and `method="sigmoid"`, keep the lower-Brier one. Use calibrated (or verified-raw) P(R) as the score and feed it to the shared no-call logic: `no-call` when calibrated p is in ~0.4–0.6, when the genome is out-of-distribution, or when the target gate fires. Show reliability before and after any calibration.

## Metrics to report
On the held-out grouped `test` split and per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report the expected drop on unseen clusters. Save per-antibiotic metrics to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python using CatBoost (catboost, CatBoostClassifier) that trains a gradient-boosted tree classifier, one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training so generalization is reported honestly.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one CatBoost model per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit any probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you use early stopping (recommended), the eval_set MUST be carved from TRAIN using GroupKFold on cluster_id — never a random split, and never cal or test — so no cluster spans train and eval.
- Handle class imbalance with auto_class_weights="Balanced" (or explicit class_weights). Do NOT use SMOTE/synthetic oversampling.
- CatBoost is OFTEN closer to calibrated out of the box thanks to ordered boosting, but DO NOT assume it — verify the reliability diagram and Brier on test. If calibration is off, wrap the fitted model in CalibratedClassifierCV(cv="prefit") fit on the cal split; try method="isotonic" and method="sigmoid" and keep the lower-Brier one. Use the (calibrated or verified-raw) probability of R as the score, and report reliability before vs after.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): depth (4-8), learning_rate (0.01-0.3), iterations (200-2000 with od_type/od_wait early stopping), l2_leaf_reg (1-10), auto_class_weights ("Balanced"), and optionally random_strength and bagging_temperature.

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the (calibrated) probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. You may compute SHAP/feature importance for explanation, but clearly label it as STATISTICAL association, NOT biological causation.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a boosted-tree model memorize lineage structure even with ordered boosting, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_seed) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
