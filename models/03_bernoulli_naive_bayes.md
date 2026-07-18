# Bernoulli Naive Bayes

> **One-liner:** A probabilistic classifier built specifically for binary presence/absence features, modeling each AMR gene as an independent Bernoulli variable to produce a fast per-antibiotic R/S probability.
> **Category:** linear / probabilistic ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial

## Why it fits Genome Firewall
The feature matrix is exactly what Bernoulli NB was designed for — every column is a 0/1 presence/absence indicator of a gene or point mutation, no scaling or encoding needed. It is a genuine generative probabilistic model, so it emits probabilities directly and is often surprisingly well-calibrated out of the box, which matters when calibration is the judged priority. It is essentially free to train and evaluate on a few hundred genomes, giving a strong, honest probabilistic baseline that judges rarely see applied to genomic AMR data.

## When to prefer it / when to skip it
Prefer it as a cheap, fast probabilistic counterpoint to logistic regression: it can be dropped in for every antibiotic at near-zero cost and sometimes calibrates better than a discriminative model on very small samples. Skip it (or down-weight its conclusions) when gene co-occurrence clearly matters, because its core feature-independence assumption is violated by clonal gene linkage — logistic regression (files 01/02) will usually model those interactions better. Use it as a sanity check and a diversity member in any ensemble comparison, not as the sole production model.

## Data interface (the contract this code must respect)
- Reads `data/processed/features.parquet` (index `genome_id`, binary int8 columns) directly as X — Bernoulli NB expects binary features, so no scaling.
- Reads `data/processed/labels.csv`, filtered per antibiotic; maps R→1, S→0.
- Reads `data/processed/splits.json` for grouped train/cal/test and `cluster_id`; never re-split randomly.
- Fit on **train** only; calibrate on **cal** only; report metrics on **test** only.
- Reads `db/drugs_saureus.csv` for the downstream target gate.

## Adversarial checks it must survive
- **No leakage (Rule 1):** Use `splits.json` verbatim; verify no `cluster_id` spans splits. Tune `alpha` and `fit_prior` with GroupKFold on `cluster_id` inside train only.
- **Feature-independence violation (the honest caveat):** Bernoulli NB assumes genes are conditionally independent given the label, but *S. aureus* is clonal so genes co-occur within lineages — this double-counts correlated evidence and can inflate confidence. State this limitation explicitly; it is the model's main weakness and mitigating it is part of why we also calibrate on `cal`.
- **Calibration (Rule 2):** NB's raw scores can be over-confident precisely because of the independence violation; recalibrate on `cal` and report Brier + reliability on `test` — do not trust the raw posterior as-is.
- **Honest explanations (Rule 5):** Per-feature log-likelihood ratios indicate statistical association with resistance for this dataset, not causation; separate catalog-confirmed markers (`known_markers`) from statistical-only signal.
- **Priors under imbalance:** With `fit_prior=True` the class prior tracks the training base rate, which can be misleading if test clusters differ; report per-group metrics on unseen clusters.

## Hyperparameters worth sweeping
- `alpha` (Laplace/Lidstone smoothing): grid `[0.01, 0.1, 0.5, 1.0, 2.0]` — smoothing matters a lot for rare genes seen in few genomes.
- `fit_prior`: `True` vs `False` (uniform prior) — with imbalanced classes, compare both and report which calibrates better.
- `binarize=None` (features are already binary; do not re-threshold).
- Optionally set `class_prior` explicitly if the training base rate is a poor estimate of deployment prevalence.
- Select over the grid with GroupKFold on `cluster_id` **within train only**.

## Calibration & no-call handling
Fit BernoulliNB on train, then wrap in `CalibratedClassifierCV(cv="prefit")` fit on the **cal** split — isotonic or sigmoid; because NB tends to be over-confident, calibration usually improves Brier meaningfully here, so always compare raw vs calibrated on cal. The calibrated probability feeds the no-call band (~0.4–0.6), the OOD check, and the target gate (drug target absent → no "likely to work" from marker absence alone).

## Metrics to report
On held-out grouped **test**, and **per genetic group** (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, no-call rate + accuracy-on-called. Model-specific note: report Brier **before and after** calibration to show how much the independence-driven over-confidence was corrected. Report headline metrics as a **delta versus the L2 baseline (file 01)**.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, pandas, numpy, matplotlib) that trains a BERNOULLI NAIVE BAYES classifier, which is purpose-built for binary presence/absence features.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. Train ONE model PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
2. Fit the model on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json. For hyperparameter selection use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
4. Handle class imbalance via the prior (fit_prior / class_prior) — do NOT use SMOTE or synthetic oversampling.
5. Emit calibrated probabilities and implement a no-call rule: return "no-call" when the calibrated probability is in the ambiguous band ~0.4-0.6. Also expose a target-gate hook (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

MODEL SPECIFICS:
- Use sklearn.naive_bayes.BernoulliNB. Features are already binary so pass binarize=None; do NOT scale.
- Sweep alpha in [0.01, 0.1, 0.5, 1.0, 2.0] and fit_prior in {True, False}. Select by GroupKFold(cluster_id) on the train split only, scoring by Brier (lower better).
- IMPORTANT honest caveat to encode in comments/output: Bernoulli NB assumes conditional feature independence, which is violated by clonal gene co-occurrence in S. aureus and can cause over-confidence. Therefore ALWAYS calibrate and report Brier BEFORE and AFTER calibration.
- Calibrate the fitted model with CalibratedClassifierCV(cv="prefit") on the cal split (isotonic or sigmoid; pick per antibiotic by cal Brier).
- Per-feature log-likelihood ratios may be reported as interpretability, but state clearly they are statistical associations for this dataset, NOT biological causation, and cross-reference against known_markers from drugs_saureus.csv.

OUTPUT / METRICS:
- On the TEST split, and PER genetic group (cluster_id) including unseen clusters, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic. Report Brier before vs after calibration.
- Save per-antibiotic metrics to a dict and to JSON (e.g. reports/metrics_bernoulli_nb.json).
- Print a clean summary table (rows = antibiotics, columns = the metrics above).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
