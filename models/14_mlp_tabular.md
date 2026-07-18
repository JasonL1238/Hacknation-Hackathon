# Multilayer Perceptron (tabular MLP)

> **One-liner:** A small feed-forward neural network trained directly on the binary presence/absence matrix.
> **Category:** tabular-DL ·
> **Runs on:** local CPU/GPU ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
An MLP can in principle learn non-linear interactions between AMR genes and point mutations (e.g. a marker that only matters when a co-factor gene is present) that a linear model would miss. The inputs are already numeric int8 binary columns, so no encoding is needed. That said, each per-antibiotic dataset is small, sparse, and imbalanced, which is a hostile setting for an unconstrained neural net — so the MLP is included as an honest test of whether any non-linear structure exists beyond what logistic regression captures, not as an expected winner.

## When to prefer it / when to skip it
Reach for the MLP only after logistic regression and tree ensembles are in place, to check whether heavy-regularized non-linearity adds anything. Skip it when data is very small or when you need interpretability or trustworthy calibration with minimal effort (prefer logistic regression or TabPFN). Set expectations honestly up front: on data of this size and sparsity the MLP is **unlikely to beat logistic regression**, and if it appears to, suspect overfitting or leakage before believing it.

## Data interface (the contract this code must respect)
- Read `data/processed/features.parquet` (index `genome_id`, int8 binary columns) as X.
- Read `data/processed/labels.csv`; per antibiotic build the R/S target aligned to feature rows.
- Read `data/processed/splits.json` for `train` / `cal` / `test` and `cluster_id`.
- Train (weights + early stopping) using the **train** split ONLY; carve the early-stopping validation set from **train** via GroupKFold on `cluster_id`. Calibrate on **cal** ONLY. Report metrics on **test** ONLY.
- Never touch `cal`/`test` during training or early stopping; never let a cluster span splits.

## Adversarial checks it must survive
- **Leakage (rule 1):** the early-stopping / model-selection validation set must be carved from train by GroupKFold on `cluster_id`, never a random split — otherwise the net will tune to leaked clonal neighbors. `cal` and `test` are untouched during training.
- **Overfitting to clonality:** a flexible net easily memorizes lineage. Force heavy regularization (dropout, weight decay, small width, early stopping) and compare test performance on seen vs unseen clusters; a large seen/unseen gap signals memorization.
- **Calibration (rule 2):** raw neural-net softmax/sigmoid outputs are typically overconfident. Apply temperature scaling fit on `cal` and report Brier + reliability on `test` before and after.
- **Class imbalance (protocol 4):** use a class-weighted loss (e.g. `pos_weight` in BCEWithLogitsLoss) rather than synthetic oversampling across the grouped structure.
- **Honest explanation (rule 5):** the MLP offers no reliable causal attribution; any saliency is statistical only. User-facing supporting genes come from the catalog/target gate.
- **Generalization (rule 6):** report per-group metrics including unseen clusters and state the drop.

## Hyperparameters worth sweeping
- Hidden layer sizes / depth: keep small, e.g. one or two layers of `{16, 32, 64}` units — avoid wide nets on this data.
- `dropout`: 0.2–0.6 (lean high given sparsity).
- `weight_decay` (L2): 1e-4 to 1e-1.
- Learning rate: 1e-4 to 1e-2 (Adam).
- Early-stopping patience and max epochs; batch size (small, e.g. 16–64).
- Class-weight / `pos_weight` scaling for imbalance.
Select with GroupKFold on `cluster_id` within **train**.

## Calibration & no-call handling
Train with a class-weighted BCE loss and early stopping on the grouped train-derived validation set. Then apply temperature scaling (a single scalar fit by minimizing NLL on `cal`) — cheap and effective for neural nets. Feed calibrated p into the no-call band (~0.4–0.6) plus the pipeline's OOD and target-gate no-calls. Report no-call rate and accuracy-on-called on `test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called — on the held-out grouped **test** split and per genetic group (including unseen clusters). Model-specific: report calibration before and after temperature scaling, and report the seen-vs-unseen-cluster gap as an overfitting check. State plainly how it compares to the logistic-regression baseline.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S) to that antibiotic, with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION quality (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

Write complete, runnable Python that trains a small MULTILAYER PERCEPTRON (feed-forward neural net) on the binary presence/absence matrix, per antibiotic. Use PyTorch (or sklearn MLPClassifier if simpler), with heavy regularization suited to small sparse data. Be honest: this is unlikely to beat logistic regression here, and the code should make that comparison possible.

DATA CONTRACT (assume these files exist, paths as given):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Union of columns across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant / likely-to-fail, S = susceptible / likely-to-work), source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

PROTOCOL (obey exactly):
1. Train one model PER antibiotic (loop over antibiotics in labels.csv).
2. Fit the MLP on the TRAIN split ONLY. If you need a validation set for early stopping / model selection, carve it FROM THE TRAIN split using GroupKFold on cluster_id — never touch cal or test. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json.
4. Handle class imbalance with a class-weighted loss (e.g. pos_weight in BCEWithLogitsLoss); do NOT use SMOTE-style synthetic oversampling.

MODEL SPECIFICS:
- Small architecture: 1-2 hidden layers of width in {16,32,64}, ReLU, with dropout (0.2-0.6) and weight decay (1e-4 to 1e-1). Adam, lr in {1e-4..1e-2}, small batch size (16-64), early stopping on the grouped train-derived validation loss.
- Sweep hidden size, dropout, learning rate, and weight_decay via GroupKFold on cluster_id within TRAIN.
- Calibrate with temperature scaling: fit a single scalar temperature by minimizing NLL on CAL, then apply to test logits. Report Brier + reliability BEFORE and AFTER temperature scaling.
- Implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6 (the pipeline also has OOD and target-gate no-calls, which you can stub as hooks).

REPORTING:
- On the TEST split, report per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and a reliability diagram. Also report no-call rate and accuracy-on-called.
- Report metrics broken down PER GENETIC GROUP, explicitly separating test clusters SEEN vs UNSEEN in training, and print the performance drop on unseen clusters (a large seen/unseen gap indicates overfitting to clonal structure).
- Save per-antibiotic metrics to a dict and dump to JSON, then print a summary table across antibiotics. If a logistic-regression baseline is available, include a note comparing to it.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate any data. The MLP gives no trustworthy causal attribution, so do not present any saliency as biological causation. Output one self-contained script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
