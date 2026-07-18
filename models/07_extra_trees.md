# Extremely Randomized Trees (sklearn ExtraTreesClassifier)

> **One-liner:** A tree ensemble like Random Forest but with randomized split thresholds and (by default) no bootstrap, trading a little bias for lower variance on sparse binary features.
> **Category:** tree-ensemble ·
> **Runs on:** local CPU ·
> **Priority:** stretch ·
> **Interpretable:** partial (Gini/permutation importances — statistical, not causal)

## Why it fits Genome Firewall
Extra Trees chooses split thresholds at random rather than searching for the locally optimal cut, which reduces variance and can help on our high-variance, sparse binary AMR matrix where many columns are near-constant and each per-antibiotic label set is small. Like Random Forest, it captures gene×gene interactions (e.g. a resistance gene that only matters alongside a target mutation) without manual feature crosses, and it is fast enough to sweep freely on CPU. Because calibration is the judged priority and these averaged-vote probabilities tend to be under-confident, we treat raw `predict_proba` as unusable and fix it with isotonic calibration on `cal`.

## When to prefer it / when to skip it
Prefer Extra Trees over Random Forest when RF is overfitting the training clusters and you want the extra randomization to smooth predictions, or when you want a faster ensemble to sweep widely on limited CPU. It sometimes edges out RF on very high-variance sparse features. Skip it when a boosting model already wins cleanly on the per-genetic-group breakdown and Brier score, or when you need the marginally sharper decision boundaries that optimal-threshold trees (RF/boosting) can give on the markers that genuinely separate R from S. Treat it as a stretch alternative to the RF baseline, not a primary submission model.

## Data interface (the contract this code must respect)
- Read features from `data/processed/features.parquet` — one row per genome, index `genome_id` (str); all columns int8 binary presence/absence; absent = 0; no missing values.
- Read labels from `data/processed/labels.csv` — `genome_id`, `antibiotic`, `label` ∈ {`R`,`S`}, `source`, `method`; one row per (genome_id, antibiotic).
- Read splits from `data/processed/splits.json` — `genome_id` → `{"split", "cluster_id"}`; grouped by genetic cluster, no cluster spans splits.
- Read `db/drugs_saureus.csv` for the downstream target gate.
- Train one Extra Trees model **per antibiotic**. Fit on `train`, calibrate on `cal`, report metrics on `test`. Never re-split randomly; any internal validation set comes from `train` via GroupKFold on `cluster_id`.

## Adversarial checks it must survive
- **Leakage / clonal memorization (rigor rule 1 & 6):** Even with randomized splits, a deep, wide Extra Trees ensemble can latch onto lineage/clonal structure that co-occurs with resistance in a clonal organism like *S. aureus* and appear excellent on within-lineage evaluation. The grouped `cluster_id` split exists to break this — respect it and judge the model on the **per-genetic-group breakdown, especially unseen clusters**, plus Brier, not aggregate accuracy. Carve any early-stopping/tuning validation set from `train` via GroupKFold on `cluster_id`; never touch `cal` or `test`.
- **Poor / skewed calibration (rigor rule 2):** Extra Trees probabilities are averaged votes and are typically under-confident; isotonic calibration fit on `cal` is usually needed, with Brier + reliability reported on `test`.
- **Importances are not causation (rigor rule 5):** because splits are random, its native importances are even noisier than RF's; prefer permutation importance on a train-derived GroupKFold fold and still label results statistical-only, cross-checking named markers against `known_markers` in `db/drugs_saureus.csv`.
- **Absence-of-markers overconfidence (rigor rule 4):** a confident "S" from all-zero markers must pass the deterministic target gate before becoming "likely to work."
- **Imbalance:** use `class_weight="balanced"`/`"balanced_subsample"`; do not use SMOTE across the grouped structure.

## Hyperparameters worth sweeping
- `n_estimators`: 300–1000 (more trees stabilize the averaged probabilities, aiding calibration).
- `max_depth`: None vs a 4–16 cap — capping fights clonal memorization on unseen clusters.
- `min_samples_leaf`: 1, 2, 5, 10 — larger leaves smooth probabilities on tiny classes.
- `max_features`: "sqrt", "log2", or 0.1–0.3 — low values suit the sparse binary matrix.
- `bootstrap`: False (default) vs True (enables `max_samples` and out-of-bag estimates).
- `class_weight`: "balanced" vs "balanced_subsample".
Select over these with GroupKFold on `cluster_id` **within train**, scoring Brier and balanced accuracy.

## Calibration & no-call handling
Fit Extra Trees on `train`, then wrap with `CalibratedClassifierCV(..., method="isotonic", cv="prefit")` fit on `cal`. Isotonic is the default choice because these trees are under-confident and monotonically miscalibrated, and `cal` is a dedicated held-out set. Use the calibrated probability of `R` as the score and feed it into the shared no-call logic: `no-call` when calibrated p is in ~0.4–0.6, when the genome is out-of-distribution, or when the target gate fires. Show reliability diagrams before and after calibration.

## Metrics to report
On the held-out grouped `test` split and per genetic group (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report the expected drop on unseen clusters. Save per-antibiotic metrics to JSON and print a summary table.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building a STRICTLY DEFENSIVE research prototype called Genome Firewall. Given a reconstructed Staphylococcus aureus genome, it predicts, per antibiotic, whether the bug is resistant (R = likely-to-fail) or susceptible (S = likely-to-work), with a CALIBRATED confidence. It only explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) — an honestly calibrated, non-leaky model beats a flashier overconfident one.

Write complete, runnable Python (scikit-learn) that trains an EXTRA TREES classifier (ExtraTreesClassifier — extremely randomized trees, randomized split thresholds), one model PER antibiotic, on my data. Use these exact input files:

1. data/processed/features.parquet — one row per genome, index = genome_id (str). Every column is an int8 BINARY presence/absence (0/1) of an AMR gene symbol (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) or a named point mutation (e.g. gyrA_S84L, grlA_S80F). Columns are the union across the dataset; absent = 0; NO missing values. Expect tens-to-low-hundreds of sparse binary columns and hundreds-to-low-thousands of genomes.
2. data/processed/labels.csv — columns: genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are IMBALANCED.
3. data/processed/splits.json — maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training so generalization is reported honestly.
4. db/drugs_saureus.csv — columns: antibiotic, drug_class, target_genes (;-separated), known_markers (;-separated), standardized_name.

PROTOCOL you MUST obey:
- Train one Extra Trees model per antibiotic (loop over antibiotics in labels.csv). Align each genome's feature row to its label by genome_id.
- Fit on the TRAIN split ONLY. Fit probability CALIBRATION on the CAL split ONLY. Report ALL metrics on the TEST split ONLY (held out).
- NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you need an internal validation set for hyperparameter selection, carve it from TRAIN using GroupKFold on cluster_id; never touch cal or test.
- Handle class imbalance with class_weight="balanced" or "balanced_subsample". Do NOT use SMOTE/synthetic oversampling.
- Extra Trees probabilities are typically UNDER-confident, so calibrate: wrap the fitted model in CalibratedClassifierCV(method="isotonic", cv="prefit") fit on the cal split. Use the calibrated probability of R as the score.

SWEEP (via GroupKFold on cluster_id within TRAIN, scoring Brier + balanced accuracy): n_estimators (300-1000), max_depth (None or 4-16), min_samples_leaf (1,2,5,10), max_features ("sqrt","log2",0.1-0.3), bootstrap (False vs True), class_weight ("balanced" vs "balanced_subsample").

OUTPUT for each antibiotic, computed on the held-out TEST split AND broken down per genetic group (cluster_id), including clusters unseen in training: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and data to plot a reliability diagram (predicted vs observed frequency by bin). Also implement a NO-CALL rule: return "no-call" when the calibrated probability of R is in the ambiguous band ~0.4-0.6, when the genome looks out-of-distribution, or when a deterministic target gate fires (never output "likely to work" from absence of resistance markers alone — the drug's target_genes from drugs_saureus.csv must be present). Report no-call rate and accuracy-on-called. Plot reliability diagrams before vs after calibration.

Save the per-antibiotic metrics to a dict and to JSON, and print a summary table across antibiotics. Emphasize the per-genetic-group breakdown (especially unseen clusters) and the Brier score, not just aggregate accuracy — a clonal organism like S. aureus lets a tree ensemble memorize lineage structure, so aggregate numbers can look deceptively good. Keep the code reproducible (fixed random_state) and self-contained.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
