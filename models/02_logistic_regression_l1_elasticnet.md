# L1 / Elastic-Net Logistic Regression

## Current status and duplicate policy

Pure L1 is already implemented and tested in the completed ensemble. Elastic Net is the
next experiment. It must reuse the committed Mash split, group every internal fold by
`cluster_id`, and weight each labeled row by `1 / labeled dedup-group size`.

> **One-liner:** A sparsity-inducing linear classifier (`saga` solver) that drives most gene coefficients to exactly zero, leaving only the few driver genes behind each per-antibiotic R/S call.
> **Category:** linear ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** yes

## Why it fits Genome Firewall
The feature matrix has many correlated and rare binary columns — genes that travel together within a clone, or point mutations seen in a handful of genomes — and L1/Elastic-net regularization is purpose-built to collapse that redundancy, keeping only the columns that carry independent signal for a given drug. That yields a short, honest explanation per antibiotic ("this call rests on `mecA`, everything else zeroed out") which is exactly the interpretability story judges reward. It stays a linear probabilistic model, so its outputs calibrate cleanly on the `cal` split for the calibration-first scoring, and it runs on CPU in seconds per antibiotic.

## When to prefer it / when to skip it
Prefer it over the L2 baseline (file 01) when the goal is to **identify which genes actually drive each drug's call** and to prune the many correlated/rare columns down to a compact driver set. Elastic-net (`0 < l1_ratio < 1`) is the safer default over pure L1 when driver genes are correlated, because pure L1 arbitrarily picks one of a correlated group and zeros its partners — which can mislead the explanation. Skip it if the L2 baseline already generalizes better on the grouped-test Brier and you do not need feature selection; L1's aggressive pruning can hurt calibration on very small per-antibiotic samples.

## Data interface (the contract this code must respect)
- Reads `data/processed/features.parquet` (index `genome_id`, binary int8 columns) as X.
- Reads `data/processed/labels.csv`, filtered per antibiotic; maps R→1, S→0.
- Reads `data/processed/splits.json` for split, `cluster_id`, and `dedup_group_id`; never re-split randomly.
- Fit on **train** only; calibrate on **cal** only; report metrics on **test** only.
- Reads `db/drugs_saureus.csv` for the downstream target gate.

## Adversarial checks it must survive
- **No leakage (Rule 1):** Use `splits.json` verbatim; verify no `cluster_id` or `dedup_group_id` spans splits. Select `C` and `l1_ratio` with grouped folds inside train only.
- **Duplicate control:** fit, tune, calibrate, and evaluate with normalized inverse labeled-family weights; also report ordinary metrics.
- **Calibration (Rule 2):** Sparse solutions can shift the probability scale; calibrate on `cal`, report Brier + reliability on `test`.
- **Honest explanations (Rule 5):** The surviving nonzero coefficients are the "driver genes" only in a **statistical** sense for this dataset — not proof of causation. Cross-reference the selected genes against `known_markers` in `drugs_saureus.csv`, and clearly separate catalog-confirmed markers from statistical-only survivors. Report selection stability across GroupKFold folds so a single lucky fold does not define the driver set.
- **Correlated-gene arbitrariness:** Pure L1 zeroing one of two co-occurring genes is a modeling artifact, not biology. Mitigate by using elastic-net and by reporting the correlated cluster, not just the winner.
- **Convergence pitfalls:** `saga` needs care — see hyperparameters — or coefficients can silently be junk.

## Hyperparameters worth sweeping
- `penalty`: `"l1"` and `"elasticnet"` (elasticnet requires `solver="saga"`).
- `l1_ratio`: grid over `[0.1, 0.3, 0.5, 0.7, 0.9, 1.0]` (1.0 = pure L1).
- `C` (inverse regularization): logspace `1e-2 … 1e2`.
- `class_weight="balanced"`.
- `solver="saga"`, `max_iter` high (e.g. 5000) and check `n_iter_` for convergence; **standardize/scale features** or at least raise `max_iter` and tighten `tol`, since `saga` convergence is sensitive to feature scaling even for binary columns.
- Select over the `(C, l1_ratio)` grid with GroupKFold on `cluster_id` **within train only**.

## Calibration & no-call handling
Fit the sparse model on train, then calibrate on the **cal** split via `CalibratedClassifierCV(cv="prefit")` (isotonic if cal is large enough, else sigmoid/Platt). The calibrated probability feeds the no-call band (~0.4–0.6). Because L1 may zero out every feature for a genome (predicting near the base rate), such near-base-rate predictions should also tend toward `no-call`; combine with the OOD check and the target gate (drug target absent → no "likely to work" from marker absence).

## Metrics to report
On held-out grouped **test**, and **per genetic group** (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, no-call rate + accuracy-on-called. Model-specific additions: number of nonzero coefficients (sparsity) per antibiotic, and the selected driver-gene list with its selection-stability across folds. Report all headline metrics as a **delta versus the L2 baseline (file 01)**.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, pandas, numpy, matplotlib) that trains an L1 / ELASTIC-NET LOGISTIC REGRESSION whose value is automatic sparse driver-gene selection.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int, "dedup_group_id": int, "dedup_group_size": int}. Neither a cluster nor duplicate family spans splits.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. Train ONE model PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
2. Fit the model on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. For hyperparameter selection use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
4. Handle class imbalance with class_weight="balanced". Do NOT use SMOTE or synthetic oversampling.
5. Pass normalized sample_weight = 1 / labeled dedup-group size in fitting and calibration, and use those weights for duplicate-weighted metrics.
6. Emit calibrated probabilities and implement a no-call rule: return "no-call" when the calibrated probability is in the ambiguous band ~0.4-0.6. Also expose a target-gate hook (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

MODEL SPECIFICS:
- Use sklearn.linear_model.LogisticRegression with solver="saga", class_weight="balanced", max_iter=5000, and check convergence (n_iter_). Standardize features before fitting to help saga converge.
- Sweep penalty in {"l1","elasticnet"}, l1_ratio in [0.1,0.3,0.5,0.7,0.9,1.0], and C in np.logspace(-2, 2, 10). Select (C, l1_ratio, penalty) by GroupKFold(cluster_id) on the train split only, scoring by Brier (lower better).
- Calibrate the fitted model with CalibratedClassifierCV(cv="prefit") on the cal split (isotonic or sigmoid; pick per antibiotic by cal Brier).
- Because this model's selling point is feature selection, report the NONZERO coefficients per antibiotic (the "driver genes"), their sign, and how stable that selection is across the GroupKFold folds. Explicitly state that a nonzero coefficient is a statistical association for this dataset, NOT biological causation, and cross-reference selected genes against known_markers from drugs_saureus.csv (separating catalog-confirmed from statistical-only).

OUTPUT / METRICS:
- On the TEST split, and PER genetic group (cluster_id) including unseen clusters, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic. Also report the sparsity (count of nonzero coefficients) per antibiotic.
- Save per-antibiotic metrics and the selected driver-gene lists to a dict and to JSON (e.g. reports/metrics_logreg_l1_enet.json).
- Print a clean summary table (rows = antibiotics, columns = the metrics above plus nonzero-coefficient count).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
