# TabNet

> **One-liner:** An attention-based deep tabular model that uses sequential, learnable feature masks to decide which features to attend to at each decision step.
> **Category:** tabular-DL (attention) ·
> **Runs on:** local CPU/GPU (GPU helps) ·
> **Priority:** stretch ·
> **Interpretable:** partial (feature masks — statistical, not causal)

## Why it fits Genome Firewall
TabNet's sequential attention picks a sparse subset of features per decision step, which is a natural match for a sparse binary AMR matrix where only a handful of genes/mutations drive resistance to any given drug. Its feature masks give a built-in, if limited, form of interpretability — you can see which columns it attended to. It is included to test the specific question "does attention-style feature selection buy anything over logistic regression / gradient-boosted trees on this data?" — with the honest prior that TabNet is data-hungry and likely to underperform on small per-antibiotic sets.

## When to prefer it / when to skip it
Consider TabNet when you want an attention model with some feature-level transparency and you have a GPU to make sweeps affordable. Skip it as a primary model on this data: with only hundreds-to-low-thousands of genomes it will likely lose to simpler, better-calibrated models, and its masks describe correlation, not mechanism. Report its result plainly whether it helps or not — a null result here is a legitimate, publishable finding for the rigor story.

## Data interface (the contract this code must respect)
- Read `data/processed/features.parquet` (index `genome_id`, int8 binary columns) as X.
- Read `data/processed/labels.csv`; per antibiotic build the R/S target aligned to feature rows.
- Read `data/processed/splits.json` for `train` / `cal` / `test` and `cluster_id`.
- Fit on **train** ONLY; carve TabNet's `eval_set` / early-stopping validation from **train** via GroupKFold on `cluster_id`. Calibrate on **cal** ONLY. Report metrics on **test** ONLY.
- Never let a cluster span splits; never use `cal`/`test` for early stopping.

## Adversarial checks it must survive
- **Leakage (rule 1):** TabNet's built-in early stopping wants an eval set — it MUST come from a GroupKFold split of train on `cluster_id`, never a random slice and never `cal`/`test`. A random eval set leaks clonal neighbors.
- **Overfitting on small data:** TabNet is data-hungry; on this size it can overfit or train unstably. Use strong `lambda_sparse`, modest `n_steps`, small `n_d`/`n_a`, and early stopping; compare seen-vs-unseen-cluster test performance to catch memorization.
- **Calibration (rule 2):** deep tabular models are often miscalibrated. Fit temperature scaling (or isotonic via CalibratedClassifierCV wrapping a sklearn-compatible interface) on `cal`, and report Brier + reliability on `test` before and after.
- **Interpretability honesty (rule 5):** TabNet feature masks are attention weights = statistical association, NOT biological causation. Label them explicitly as statistical-only; user-facing supporting genes come from the AMR catalog and target gate, never from masks alone.
- **Class imbalance (protocol 4):** use class weights in the loss rather than synthetic oversampling.
- **Generalization (rule 6):** report per-group metrics including unseen clusters and state the drop.

## Hyperparameters worth sweeping
- `n_d` and `n_a` (decision/attention widths): keep small, e.g. 8, 16, 24.
- `n_steps` (decision steps): 3–5.
- `gamma` (feature reuse coefficient): 1.0–2.0.
- `lambda_sparse` (sparsity regularization): 1e-4 to 1e-2 — lean higher for sparse binary inputs.
- Learning rate: 1e-3 to 2e-2 (Adam), with scheduler.
- `batch_size` / `virtual_batch_size`: modest given small data.
- Early-stopping patience and max epochs.
Select with GroupKFold on `cluster_id` within **train**.

## Calibration & no-call handling
Train TabNet with class weights and early stopping on the grouped train-derived eval set. Because its raw probabilities are often overconfident, calibrate on `cal` (temperature scaling, or isotonic through a prefit-style wrapper). Feed calibrated p into the no-call band (~0.4–0.6) plus the pipeline's OOD and target-gate no-calls. Report no-call rate and accuracy-on-called on `test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called — on the held-out grouped **test** split and per genetic group (including unseen clusters). Model-specific: report calibration before and after calibration, the seen-vs-unseen-cluster gap, and (labeled as statistical-only) the top features by aggregated mask weight for a sanity check against the known AMR catalog.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S) to that antibiotic, with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION quality (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

Write complete, runnable Python that trains TabNet (use the pytorch-tabnet library, TabNetClassifier) per antibiotic on the binary presence/absence matrix. TabNet is an attention-based tabular model with sequential feature masks (some built-in interpretability). Be honest: it is data-hungry and likely to underperform simpler models on this small data — the goal is to test whether attention buys anything, and to report that plainly.

DATA CONTRACT (assume these files exist, paths as given):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Union of columns across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant / likely-to-fail, S = susceptible / likely-to-work), source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

PROTOCOL (obey exactly):
1. Train one model PER antibiotic (loop over antibiotics in labels.csv).
2. Fit TabNet on the TRAIN split ONLY. TabNet's early stopping needs an eval_set — carve it FROM THE TRAIN split using GroupKFold on cluster_id; never touch cal or test. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json.
4. Handle class imbalance with class weights in the loss; do NOT use SMOTE-style synthetic oversampling.

MODEL SPECIFICS:
- Sweep n_d and n_a (in {8,16,24}), n_steps (3-5), gamma (1.0-2.0), lambda_sparse (1e-4 to 1e-2), and learning rate (1e-3 to 2e-2). Use modest batch_size/virtual_batch_size and early stopping on the grouped train-derived eval set. Select via GroupKFold on cluster_id within TRAIN.
- TabNet probabilities are often overconfident: calibrate on CAL (temperature scaling, or isotonic through a prefit-style wrapper). Report Brier + reliability BEFORE and AFTER calibration.
- Implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6 (the pipeline also has OOD and target-gate no-calls, which you can stub as hooks).

REPORTING:
- On the TEST split, report per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and a reliability diagram. Also report no-call rate and accuracy-on-called.
- Report metrics broken down PER GENETIC GROUP, explicitly separating test clusters SEEN vs UNSEEN in training, and print the performance drop on unseen clusters (a large gap indicates overfitting to clonal structure).
- Extract TabNet's aggregated feature masks and print the top attended features per antibiotic, but LABEL them explicitly as statistical association only, NOT biological causation.
- Save per-antibiotic metrics to a dict and dump to JSON, then print a summary table across antibiotics.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate any data. Output one self-contained script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
