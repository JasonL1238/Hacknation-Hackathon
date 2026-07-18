# Linear Support Vector Machine

> **One-liner:** A margin-based linear classifier that separates R from S genomes in the sparse binary gene space, wrapped in a calibration layer to convert its raw scores into usable probabilities.
> **Category:** linear ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial

## Why it fits Genome Firewall
Linear SVMs are strong on sparse, high-dimensional binary data — exactly the AMR presence/absence matrix here — because the max-margin objective focuses on the genomes near the decision boundary and handles many rare columns gracefully. Its weight vector still maps onto named genes, giving partial interpretability. The critical fit-caveat is that a raw SVM emits **decision-function distances, not probabilities**, so for a calibration-first project it MUST be paired with an explicit calibration step; done right, it becomes a competitive, well-calibrated per-antibiotic classifier.

## When to prefer it / when to skip it
Prefer it when the decision boundary between resistant and susceptible genomes is close but roughly linear and you want a margin-based alternative to logistic regression for model diversity — it can be more robust to a few mislabeled genomes near the boundary. Skip it if you need first-class probabilities with no extra machinery (logistic regression, files 01/02, gives those directly) or full-strength interpretability. Never deploy `LinearSVC` outputs directly as confidence — always through the calibration wrapper below.

## Data interface (the contract this code must respect)
- Reads `data/processed/features.parquet` (index `genome_id`, binary int8 columns) as X.
- Reads `data/processed/labels.csv`, filtered per antibiotic; maps R→1, S→0.
- Reads `data/processed/splits.json` for grouped train/cal/test and `cluster_id`; never re-split randomly.
- Fit on **train** only; calibrate on **cal** only; report metrics on **test** only.
- Reads `db/drugs_saureus.csv` for the downstream target gate.

## Adversarial checks it must survive
- **No native probabilities (the critical one):** `LinearSVC` has **no** `predict_proba`, and `SVC(probability=True)` runs an internal CV that is NOT aware of our grouped split and can leak clonal structure. Mitigation: fit the base SVM on **train**, then wrap it in `CalibratedClassifierCV(cv="prefit")` fit on the **cal** split (Platt/sigmoid or isotonic). Do not use `SVC`'s built-in probability estimation.
- **No leakage (Rule 1):** Use `splits.json` verbatim; verify no `cluster_id` spans splits. Sweep `C` with GroupKFold on `cluster_id` inside train only.
- **Calibration (Rule 2):** Raw margins are not probabilities and are usually poorly calibrated; the whole point is that the calibrated output is reported with Brier + reliability on `test`.
- **Honest explanations (Rule 5):** SVM weights are statistical associations for this dataset, not causation; separate catalog markers (`known_markers`) from statistical-only weights.
- **Clonal memorization:** Margin fit can key on a lineage; report per-group metrics on unseen clusters.

## Hyperparameters worth sweeping
- `C` (regularization / margin softness): logspace `1e-3 … 1e2`.
- `class_weight="balanced"` (essential given class imbalance).
- Loss for `LinearSVC`: `"squared_hinge"` (default) vs `"hinge"`; `dual=True/False` depending on n_samples vs n_features (many features, few samples → `dual=True`).
- Calibration `method`: `"sigmoid"` (Platt, safe for small cal) vs `"isotonic"` (needs a larger cal split).
- `max_iter` raised for convergence; consider scaling even though features are binary if convergence warns.
- Select `C` (and calibration method) with GroupKFold on `cluster_id` **within train only**, scoring by Brier.

## Calibration & no-call handling
This model's calibration is mandatory, not optional: fit `LinearSVC(class_weight="balanced")` (or `SVC(kernel="linear")` **with `probability=False`**) on train, then `CalibratedClassifierCV(estimator=fitted, cv="prefit", method=...)` on the **cal** split. The resulting calibrated probability feeds the no-call band (~0.4–0.6), the OOD check, and the target gate (drug target absent → no "likely to work" from marker absence alone). Report both raw-margin behavior and calibrated Brier to show the wrapper worked.

## Metrics to report
On held-out grouped **test**, and **per genetic group** (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, no-call rate + accuracy-on-called. Model-specific note: explicitly report the calibrated Brier (raw SVM has no probability to score). Report headline metrics as a **delta versus the L2 baseline (file 01)**.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, pandas, numpy, matplotlib) that trains a LINEAR SVM. CRITICAL: a linear SVM has NO native probabilities, so it MUST be wrapped in a calibration layer fit on the cal split.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. Train ONE model PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
2. Fit the base SVM on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. For hyperparameter selection use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
4. Handle class imbalance with class_weight="balanced". Do NOT use SMOTE or synthetic oversampling.
5. Emit calibrated probabilities and implement a no-call rule: return "no-call" when the calibrated probability is in the ambiguous band ~0.4-0.6. Also expose a target-gate hook (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

MODEL SPECIFICS (the calibration is the whole point):
- Use sklearn.svm.LinearSVC(class_weight="balanced", max_iter=10000) as the base estimator (or SVC(kernel="linear") with probability=False). Do NOT use SVC's built-in probability=True, because its internal CV is not aware of our grouped split and can leak clonal structure.
- Fit the base SVM on train, then wrap the FITTED estimator in CalibratedClassifierCV(cv="prefit", method=...) and fit that on the CAL split. Compare method="sigmoid" (Platt) and method="isotonic"; pick per antibiotic by cal-split Brier.
- Sweep C in np.logspace(-3, 2, 12) via GroupKFold(cluster_id) on the train split only, scoring by Brier after calibration.
- SVM weights may be reported as interpretability, but state they are statistical associations for this dataset, NOT biological causation; cross-reference against known_markers from drugs_saureus.csv.

OUTPUT / METRICS:
- On the TEST split, and PER genetic group (cluster_id) including unseen clusters, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score (on the CALIBRATED probabilities), no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic.
- Save per-antibiotic metrics to a dict and to JSON (e.g. reports/metrics_linear_svm.json).
- Print a clean summary table (rows = antibiotics, columns = the metrics above).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
