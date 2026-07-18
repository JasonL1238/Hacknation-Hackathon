# FT-Transformer

> **One-liner:** A feature-tokenizer transformer that embeds each tabular feature as a token and applies transformer self-attention across them.
> **Category:** tabular-DL (transformer) ·
> **Runs on:** Kaggle GPU ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
FT-Transformer tokenizes each feature and lets self-attention model interactions among AMR genes and point mutations, which could in principle capture higher-order combinations of markers driving resistance. It is included as the "does a full tabular transformer help?" experiment. The honest prior is strongly negative for this dataset: transformers are data-hungry and overfit easily on hundreds-to-low-thousands of sparse binary rows, so it is expected to underperform simpler, better-calibrated models and is scoped as a stretch experiment, not a core model.

## When to prefer it / when to skip it
Only run FT-Transformer once the core linear/tree/foundation models are done and you specifically want to rule in or out whether a transformer architecture adds anything on this data — and run it on a Kaggle GPU because sweeps are expensive. Skip it whenever data is small (which it is here), when calibration and interpretability matter most (they do — prefer logistic regression / TabPFN), or when compute is limited. Treat a null or negative result as a legitimate, reportable finding.

## Data interface (the contract this code must respect)
- Read `data/processed/features.parquet` (index `genome_id`, int8 binary columns) as X — all features are binary/categorical tokens.
- Read `data/processed/labels.csv`; per antibiotic build the R/S target aligned to feature rows.
- Read `data/processed/splits.json` for `train` / `cal` / `test` and `cluster_id`.
- Fit on **train** ONLY; carve the early-stopping validation set from **train** via GroupKFold on `cluster_id`. Calibrate on **cal** ONLY. Report metrics on **test** ONLY.
- Never let a cluster span splits; never use `cal`/`test` for early stopping or tuning.
- Move the training to Kaggle GPU (upload the three processed files as a dataset).

## Adversarial checks it must survive
- **Leakage (rule 1):** the early-stopping validation set MUST be a GroupKFold-on-`cluster_id` carve-out of train — a random split leaks clonal neighbors and will inflate a transformer's apparent skill most of all. `cal`/`test` are untouched during training.
- **Overfitting (primary risk):** with this little data a transformer will overfit fast. Use small depth/width, strong dropout and weight decay, aggressive early stopping, and compare seen-vs-unseen-cluster test performance; expect and report a large drop off training lineages.
- **Calibration (rule 2):** transformer outputs are typically overconfident. Apply temperature scaling fit on `cal`; report Brier + reliability on `test` before and after. Calibration quality is the judged priority — a transformer that scores well but is overconfident loses.
- **Honest explanation (rule 5):** FT-Transformer gives no trustworthy causal attribution; attention weights are not causation. Supporting genes shown to users come from the AMR catalog and target gate.
- **Class imbalance (protocol 4):** class-weighted loss, not synthetic oversampling.
- **Generalization (rule 6):** report per-group metrics including unseen clusters and state the drop plainly.

## Hyperparameters worth sweeping
- `depth` (number of transformer blocks): keep shallow, e.g. 1–3.
- Token embedding dimension `d_token`: small, e.g. 8, 16, 32.
- `n_heads` (attention heads): 2–8 (must divide `d_token`).
- `attention_dropout` and `ffn_dropout`: 0.1–0.5 (lean high).
- Learning rate: 1e-4 to 1e-3 (AdamW), with warmup/scheduler.
- `weight_decay`: 1e-5 to 1e-1.
- Batch size (small) and early-stopping patience.
Select with GroupKFold on `cluster_id` within **train**.

## Calibration & no-call handling
Train with class-weighted loss and early stopping on the grouped train-derived validation set. Then apply temperature scaling (single scalar fit by minimizing NLL on `cal`). Feed calibrated p into the no-call band (~0.4–0.6) plus the pipeline's OOD and target-gate no-calls. Report no-call rate and accuracy-on-called on `test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called — on the held-out grouped **test** split and per genetic group (including unseen clusters). Model-specific: report calibration before and after temperature scaling, the seen-vs-unseen-cluster gap as the overfitting check, and an explicit comparison to the logistic-regression baseline so a negative result is documented honestly.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S) to that antibiotic, with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION quality (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

Write complete, runnable Python that trains an FT-Transformer (feature-tokenizer transformer for tabular data; use the rtdl library or an equivalent implementation) per antibiotic on the binary presence/absence matrix, designed to run on a Kaggle GPU. Be honest: transformers are data-hungry and easy to overfit on this small data, so it will probably NOT beat simpler models — the goal is to test whether a tabular transformer helps and report that plainly.

DATA CONTRACT (assume these files exist, paths as given):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Union of columns across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes. Treat every feature as binary/categorical.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant / likely-to-fail, S = susceptible / likely-to-work), source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

PROTOCOL (obey exactly):
1. Train one model PER antibiotic (loop over antibiotics in labels.csv).
2. Fit the FT-Transformer on the TRAIN split ONLY. For early stopping / model selection, carve a validation set FROM THE TRAIN split using GroupKFold on cluster_id; never touch cal or test. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json.
4. Handle class imbalance with a class-weighted loss; do NOT use SMOTE-style synthetic oversampling.

MODEL SPECIFICS:
- Keep the model small to fight overfitting: depth in {1,2,3}, d_token in {8,16,32}, n_heads in {2,4,8} (must divide d_token), attention_dropout and ffn_dropout in {0.1..0.5}, AdamW with lr in {1e-4..1e-3} and weight_decay in {1e-5..1e-1}, small batch size, aggressive early stopping. Sweep these via GroupKFold on cluster_id within TRAIN.
- Assume this runs on a Kaggle GPU (device="cuda"); make the three processed files loadable from a Kaggle dataset path.
- Calibrate with temperature scaling: fit a single scalar temperature by minimizing NLL on CAL, then apply to test logits. Report Brier + reliability BEFORE and AFTER temperature scaling.
- Implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6 (the pipeline also has OOD and target-gate no-calls, which you can stub as hooks).

REPORTING:
- On the TEST split, report per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and a reliability diagram. Also report no-call rate and accuracy-on-called.
- Report metrics broken down PER GENETIC GROUP, explicitly separating test clusters SEEN vs UNSEEN in training, and print the performance drop on unseen clusters (a large gap indicates overfitting to clonal structure).
- Save per-antibiotic metrics to a dict and dump to JSON, then print a summary table across antibiotics. If a logistic-regression baseline is available, include a note comparing to it so a negative result is documented.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate any data. The FT-Transformer gives no trustworthy causal attribution, so do not present attention as biological causation. Output one self-contained script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
