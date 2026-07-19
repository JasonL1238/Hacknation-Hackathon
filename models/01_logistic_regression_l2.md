# L2-Regularized Logistic Regression

## Current status and duplicate policy

This is the historical baseline and the reference for every research comparison. The
app artifact was retrained on the fixed Mash split. For any new research bakeoff, also
fit and report with `1 / labeled dedup-group size` sample weights.

> **One-liner:** A ridge-penalized linear classifier that turns AMR gene presence/absence into a per-antibiotic R/S probability, and serves as the project's reference baseline.
> **Category:** linear ·
> **Runs on:** local CPU ·
> **Priority:** core ·
> **Interpretable:** yes

## Why it fits Genome Firewall
The feature matrix is a sparse, high-dimensional table of binary AMR gene and point-mutation indicators, and resistance for most drugs is driven by a small number of well-characterized markers (e.g. `mecA` for oxacillin/cefoxitin, `ermC` for erythromycin) — exactly the regime a linear model handles cleanly. Because the task is judged first on calibration quality, a logistic model is ideal: it emits genuine probabilities that respond well to a downstream Platt/isotonic calibration step, and its coefficients map one-to-one onto named genes so every call can be explained honestly. It trains in milliseconds per antibiotic on a few hundred genomes, so it can be re-fit for every grouped split without cost.

## When to prefer it / when to skip it
This is **THE baseline every other model is compared against** — always run it, and report every other model's balanced accuracy, Brier score, and no-call rate as a **delta relative to this model**. Prefer it as the default production model unless a more complex model beats it on the held-out grouped-test Brier score by a margin that survives per-group breakdown. Reach for L1/Elastic-net (file 02) when you specifically want automatic driver-gene selection, and only escalate to kernel or tree models when nonlinear gene combinations are demonstrably needed. Do not skip this model — a fancier model that cannot beat it is evidence the extra complexity is unjustified.

## Data interface (the contract this code must respect)
- Reads `data/processed/features.parquet` (index `genome_id`, binary int8 gene/mutation columns) as X.
- Reads `data/processed/labels.csv` and filters to one antibiotic at a time; maps `label` R→1, S→0.
- Reads `data/processed/splits.json` for split, `cluster_id`, and `dedup_group_id`; never re-split randomly.
- Fit on **train** only; fit calibration on **cal** only; report all metrics on **test** only.
- Reads `db/drugs_saureus.csv` so the downstream target gate can veto a "likely-to-work" call when the drug's molecular target is absent.

## Adversarial checks it must survive
- **No leakage (Rule 1):** Use `splits.json` verbatim; confirm no `cluster_id` or `dedup_group_id` spans splits.
- **Duplicate control:** within each antibiotic/fitting subset, weight each labeled row by `1 / labeled dedup-group size` and report ordinary plus duplicate-weighted metrics.
- **Calibration (Rule 2):** Even logistic outputs can be over/under-confident under class imbalance; fit calibration on `cal` and report a reliability diagram + Brier on `test`, not on the training data.
- **Honest explanations (Rule 5):** A large coefficient on a gene is a **statistical association given this dataset**, not proof the gene causes resistance. Label catalog hits (`known_markers` in `drugs_saureus.csv`) separately from statistical-only coefficients; never present a coefficient as biological causation.
- **Clonal memorization:** Because *S. aureus* is highly clonal, a coefficient may be tracking a lineage rather than a mechanism. Mitigate by reporting per-genetic-group metrics (including unseen clusters) and flagging genes that only ever co-occur within one cluster.
- **No forced calls (Rule 3):** Feed calibrated probabilities into the no-call band rather than thresholding hard at 0.5.

## Hyperparameters worth sweeping
- `C` (inverse regularization strength): logspace `1e-3 … 1e2` (e.g. `np.logspace(-3, 2, 12)`). Smaller C = stronger shrinkage, useful given sparse rare columns.
- `class_weight="balanced"` (default on; also try explicit per-drug weights for very skewed antibiotics).
- `solver`: `liblinear` (robust for small/sparse binary) or `lbfgs`; both support L2.
- `penalty="l2"`, `max_iter` raised (e.g. 1000) to guarantee convergence.
- Select `C` with GroupKFold on `cluster_id` **inside the train split only** — never touch `cal` or `test`.

## Calibration & no-call handling
Wrap the fitted estimator in `CalibratedClassifierCV(cv="prefit", method=...)` trained on the **cal** split, or fit an isotonic/Platt map on cal-split probabilities. Prefer isotonic if `cal` is large enough, else sigmoid/Platt for small cal splits. The calibrated probability then drives the no-call logic: return `no-call` when calibrated p falls in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution relative to training clusters, or when the target gate fires (drug target gene absent → cannot claim "likely to work" from marker absence alone).

## Metrics to report
On the held-out grouped **test** split, and broken down **per genetic group** (including groups unseen in training): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report each as an absolute value; since this is the reference model, this is the row all other models' deltas are measured against.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, pandas, numpy, matplotlib) that trains an L2-REGULARIZED LOGISTIC REGRESSION as the reference baseline.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int, "dedup_group_id": int, "dedup_group_size": int}. Neither a cluster nor duplicate family spans splits.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. Train ONE model PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
2. Fit the model on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. If you need internal validation for hyperparameter selection, use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
4. Handle class imbalance with class_weight="balanced". Do NOT use SMOTE or synthetic oversampling.
5. Pass normalized sample_weight = 1 / labeled dedup-group size in fitting and calibration, and use those weights for duplicate-weighted metrics.
6. Emit calibrated probabilities and implement a no-call rule: return "no-call" when the calibrated probability is in the ambiguous band ~0.4-0.6. Also expose a hook for a target gate (if the drug's target_genes are all absent in a genome, do not output "likely to work" from marker absence alone).

MODEL SPECIFICS:
- Use sklearn.linear_model.LogisticRegression with penalty="l2", class_weight="balanced", solver="liblinear" (or lbfgs), max_iter=1000.
- Sweep C over np.logspace(-3, 2, 12), selecting C by GroupKFold(cluster_id) on the train split only.
- Calibrate the fitted model with CalibratedClassifierCV(cv="prefit") fit on the cal split (try both method="isotonic" and "sigmoid"; pick per antibiotic by cal-split Brier).
- Report coefficients per gene as INTERPRETABILITY only, explicitly noting a coefficient is a statistical association, NOT biological causation.

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id), including clusters unseen in training, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic.
- Save per-antibiotic metrics to a dict and to JSON (e.g. reports/metrics_logreg_l2.json).
- Print a clean summary table (rows = antibiotics, columns = the metrics above).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
