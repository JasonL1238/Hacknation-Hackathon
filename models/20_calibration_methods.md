# Probability Calibration Methods (Platt / Isotonic / Beta / Temperature)

> **One-liner:** A family of post-hoc maps that turn a base model's raw scores into honest, well-calibrated probabilities — the single most judged capability in this project.
> **Category:** method ·
> **Runs on:** local CPU ·
> **Priority:** core ·
> **Interpretable:** n/a (calibration is a probability transform, not an explainer)

## Why it fits Genome Firewall
The judged priority here is calibration quality — Brier score and the reliability diagram on the held-out grouped-test split — over raw accuracy, so this method is not an optional add-on but the core of the deliverable. Every base classifier in this folder (logistic regression, random forest, gradient boosting, naive Bayes, the ESM-2 head, and any stack) emits scores that are miscalibrated in a characteristic way — linear/NB models can be over-confident under class imbalance, bagged trees are systematically under-confident and step-shaped, and neural-net logits run hot. On a small, imbalanced, per-antibiotic *S. aureus* dataset those raw `predict_proba` values cannot be trusted directly, and the downstream no-call band (~0.4–0.6) only makes sense once the probability axis is honest. Calibration is what makes a slightly-less-accurate but truthful model win.

## When to prefer it / when to skip it
**This method applies to EVERY model in this folder — never skip it.** Which calibrator to pick depends mostly on the size of the `cal` split and on the base model:
- **Platt scaling (sigmoid):** the safe default when `cal` is small (a few dozen to low hundreds of examples per antibiotic). Fits only two parameters, so it rarely overfits; ideal for the sparse per-drug label sets here.
- **Beta calibration:** a three-parameter generalization of Platt that can correct asymmetric miscalibration (common with skewed base rates) without the overfitting risk of isotonic. Prefer it over plain Platt when reliability curves are S-shaped but not symmetric, and `cal` is still modest.
- **Isotonic regression:** the most flexible (non-parametric, monotone step function) and usually the best Brier score when `cal` is large enough. **Small-data caveat: isotonic overfits a small `cal` set** — it can chase noise into a jagged step function that looks great on `cal` and worse on `test`. Prefer Platt or beta whenever `cal` per antibiotic is small.
- **Temperature scaling:** the right choice for neural-net logits (the ESM-2 head, file for the sequence model). A single scalar `T` divides the logits before softmax/sigmoid; it preserves the argmax (so accuracy is unchanged) and fixes only confidence. Use it instead of `CalibratedClassifierCV` whenever you have raw logits rather than an sklearn estimator.

## Data interface (the contract this code must respect)
- Consumes the **uncalibrated scores** of a base model already fit on the **train** split (never re-fit the base model here).
- Fits the calibration map on the **`cal`** split ONLY — the dedicated calibration set in `data/processed/splits.json`. Never fit calibration on train (optimistic) or on test (leakage).
- Reports Brier score, reliability diagram, ECE and MCE on the **`test`** split ONLY, and additionally per `cluster_id` genetic group.
- Runs once **per antibiotic**, matching the per-antibiotic base models.
- The calibrated probability of `R` is the value handed to the shared no-call logic and (via `db/drugs_saureus.csv`) the target gate.

## Adversarial checks it must survive
- **No leakage (Rule 1):** the `cal` split is grouped by `cluster_id` just like train/test — confirm no cluster appears in both the base-model's train set and the calibration set. Fitting calibration on any data the base model saw silently inflates the reliability curve.
- **Honest calibration (Rule 2):** the reliability diagram and Brier MUST come from `test`, never from the `cal` set the map was fit on — a calibrator always looks well-calibrated on its own fitting data. Report the reliability curve *before and after* calibration so the correction is visible.
- **Small-`cal` overfitting:** isotonic on a tiny `cal` set is the classic trap; pick the calibrator per antibiotic by comparing `cal`-fit → `test` Brier, and default to Platt/beta when `cal` is small. Log this choice per antibiotic in `docs/DECISIONS.md`.
- **Per-group calibration drift (Rule 6):** a map fit on the pooled `cal` split can be miscalibrated on clusters unseen in training. Report ECE per genetic group, including unseen clusters, and expect the drop.
- **Not an explainer (Rule 5):** calibration changes only the probability, never the evidence; it must not be presented as improving or validating the biological explanation.

## Hyperparameters worth sweeping
- **Method choice** per antibiotic: `sigmoid` (Platt) vs `isotonic` vs `beta` vs `temperature`, selected by `cal`→`test` Brier (or nested GroupKFold within train+cal-style protocol without touching test).
- **Temperature `T`:** optimize a single scalar by minimizing NLL of the sigmoid/softmax on the `cal` logits (e.g. L-BFGS over `T > 0`).
- **Beta calibration parameters** (`a`, `b`, `c`): fit by maximum likelihood; no manual sweep needed but check for degenerate fits on tiny `cal`.
- **Reliability-diagram binning:** number of bins for ECE/MCE (e.g. 10–15 equal-width, or equal-frequency bins for imbalanced classes) — report which binning scheme was used, since ECE is binning-dependent.

## Calibration & no-call handling
For sklearn base estimators, wrap the already-fit model with `CalibratedClassifierCV(base_estimator, cv="prefit", method="sigmoid"|"isotonic")` and call `.fit(X_cal, y_cal)`; for beta calibration use the `betacal` package (or a hand-rolled 3-parameter logistic on `logit(p)` and `logit(1-p)`). For neural nets, hold the trained network fixed and fit temperature `T` on the `cal` logits, then apply `sigmoid(logit / T)` at inference. The resulting calibrated probability of `R` feeds the no-call rule: return `no-call` when calibrated p is in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution relative to training clusters, or when the target gate fires (drug target absent → cannot claim "likely to work" from marker absence alone). Because this method wraps every base model identically, keep it in a shared utility so all models are calibrated and reported the same way.

## Metrics to report
On the held-out grouped **test** split, and per genetic group (including unseen clusters): **Brier score**, **reliability diagram** (before vs after calibration), **ECE** (Expected Calibration Error) and **MCE** (Maximum Calibration Error) as scalar reliability summaries alongside Brier, plus balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, and no-call rate + accuracy-on-called for the calibrated model. Note that method choice should be justified by the `cal`→`test` Brier comparison, reported per antibiotic.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable calibration code for this project.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible), with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

Write complete, runnable Python (scikit-learn, numpy, scipy, pandas, matplotlib; betacal optional for beta calibration) that implements and COMPARES probability-calibration methods for an already-trained base classifier: (1) Platt scaling / sigmoid, (2) Isotonic regression, (3) Beta calibration, and (4) Temperature scaling for neural-net logits. It must run one calibration per antibiotic.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. For each antibiotic, assume a base classifier is already fit on the TRAIN split ONLY (include a simple sklearn LogisticRegression(class_weight="balanced") as a stand-in base model, plus a tiny torch MLP or a synthetic-logits path to demonstrate temperature scaling). Map label R->1, S->0.
2. Fit EVERY calibration map on the CAL split ONLY. Report ALL metrics on the TEST split ONLY. NEVER fit calibration on train or test.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json.
4. For sklearn models, calibrate with CalibratedClassifierCV(base, cv="prefit", method="sigmoid") and method="isotonic", plus a beta-calibration implementation (betacal or a 3-parameter logistic on logit(p)). For neural-net logits, implement temperature scaling: hold the network fixed and fit a single scalar T>0 by minimizing NLL on the cal logits (L-BFGS), then apply sigmoid(logit/T).
5. Emit calibrated probabilities and implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6; also expose a target-gate hook (if the drug's target_genes are all absent in a genome, do not output "likely to work" from marker absence alone).

SMALL-DATA CAVEAT you must respect: isotonic regression overfits a small cal set. Select the calibration method PER antibiotic by comparing cal-fit -> test Brier, and default to Platt/beta when the cal split is small.

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id) including clusters unseen in training, compute: Brier score, ECE (Expected Calibration Error), MCE (Maximum Calibration Error), balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, and no-call rate + accuracy-on-called. State the binning scheme used for ECE/MCE.
- Plot a reliability diagram per antibiotic showing the curve BEFORE and AFTER each calibration method on the same axes.
- Save per-antibiotic, per-method metrics to a dict and to JSON (e.g. reports/metrics_calibration.json) and print a summary table (rows = antibiotic x method, columns = the metrics above), highlighting the best method per antibiotic by test Brier.

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
