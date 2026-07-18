# k-Nearest Neighbors (kNN)

> **One-liner:** A non-parametric instance-based classifier that labels a genome by majority vote of its nearest neighbors in the presence/absence feature space.
> **Category:** method (instance-based) ·
> **Runs on:** local CPU ·
> **Priority:** stretch ·
> **Interpretable:** partial

## Why it fits Genome Firewall
The feature matrix is a sparse binary presence/absence matrix of AMR genes and named point mutations, which is exactly the setting where set-similarity distances (Hamming / Jaccard) between genomes are meaningful and cheap to compute. kNN needs no training and gives a natural, honest diagnostic: because *S. aureus* genomes cluster by clonal lineage, a nearest-neighbor vote largely re-reads clonal similarity rather than the specific resistance mechanism. That makes kNN valuable here not as a deployment model but as a **negative control** that quantifies how much apparent predictive signal is "just clonality" — a direct probe of the leakage question the judges care about.

## When to prefer it / when to skip it
Use kNN as a diagnostic baseline to answer "does a lineage-lookup do just as well as my real model?" and to derive an out-of-distribution (OOD) signal from distance-to-neighbors. Skip it as a serious contender: it does not model per-feature effects, its probabilities (vote fractions) are coarse and poorly calibrated by default, and its apparent skill on any split where lineages leak across train/test is misleading. If kNN matches your logistic-regression / tree models on the grouped test split, that is a warning that those models may be riding clonality too, not an endorsement of kNN.

## Data interface (the contract this code must respect)
- Read `data/processed/features.parquet` (index `genome_id`, int8 binary columns) as X.
- Read `data/processed/labels.csv`; for each antibiotic build the R/S target aligned to the feature rows.
- Read `data/processed/splits.json` to assign each `genome_id` to `train` / `cal` / `test` and to record its `cluster_id`.
- Fit the neighbor index on the **train** split ONLY (neighbors are drawn only from train genomes). Calibrate on **cal** ONLY. Report metrics on **test** ONLY.
- Never re-split; never let a `cluster_id` span splits.

## Adversarial checks it must survive
- **Leakage / clonality (rigor rule 1 & this model's core risk):** neighbors must come only from the train split. If kNN scores highly on test, verify it is not simply matching same-lineage genomes — report accuracy separately for test clusters seen vs unseen in training; expect a large drop on unseen clusters and state it plainly.
- **Calibration (rule 2):** raw vote fractions from small k are lumpy (only k+1 possible values) and overconfident at the extremes. Wrap the classifier in probability calibration fit on `cal` and report Brier + reliability on `test`.
- **Honest no-call (rule 3):** use distance-to-nearest-neighbors as an explicit OOD trigger — genomes whose nearest train neighbor is far (few shared markers) should route to `no-call` rather than get a confident vote.
- **Honest explanation (rule 5):** "these neighbors voted R" is an association, not a mechanism. Never present neighbor identity as biological causation; the supporting genes reported to users must come from the catalog/target-gate logic, not from kNN's vote.
- **Generalization (rule 6):** report per-genetic-group metrics; kNN is expected to degrade sharply off the training lineages, which is the point of including it.

## Hyperparameters worth sweeping
- `n_neighbors` (k): 1, 3, 5, 7, 11, 15 — small k memorizes lineage, larger k smooths.
- `weights`: `uniform` vs `distance`.
- `metric`: `hamming` and `jaccard` (both suited to binary presence/absence); optionally `dice`. Use `algorithm="brute"` with these metrics on sparse binary data.
- Class imbalance: kNN has no `class_weight`; compensate with `weights="distance"` and by tuning the decision threshold on `cal`, or by reporting balanced accuracy rather than accuracy.
- Sweep k and metric with GroupKFold on `cluster_id` carved from the **train** split only.

## Calibration & no-call handling
Fit the raw kNN on train, then calibrate probabilities on the `cal` split with `CalibratedClassifierCV(estimator, method="isotonic" or "sigmoid", cv="prefit")`. Feed calibrated p into the downstream no-call band (~0.4–0.6). Add a model-specific OOD no-call: compute the mean distance to the k nearest train neighbors for each test genome and route genomes beyond a `cal`-derived distance percentile (e.g. the 95th percentile of cal distances) to `no-call` regardless of vote. Never let the target gate be overridden by a neighbor vote.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called — all on the held-out grouped **test** split and broken down per genetic group (seen vs unseen clusters). Model-specific: also report the distribution of distance-to-nearest-train-neighbor and how much accuracy is concentrated in low-distance (same-lineage) test genomes.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S) to that antibiotic, with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION quality, not raw accuracy.

Write complete, runnable Python (scikit-learn) that trains a k-Nearest Neighbors classifier as a DIAGNOSTIC / negative-control model. The key honest point: with genetic clustering, kNN largely re-reads clonal lineage similarity, so it reveals how much apparent signal is "just clonality". Treat it accordingly.

DATA CONTRACT (assume these files exist, paths as given):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Union of columns across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant / likely-to-fail, S = susceptible / likely-to-work), source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. (You do not need the target gate for kNN itself, but keep predictions honest per the notes below.)

PROTOCOL (obey exactly):
1. Train one model PER antibiotic (loop over antibiotics in labels.csv).
2. Fit the neighbor index on the TRAIN split ONLY (neighbors drawn only from train genomes). Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json. If you need a validation set for hyperparameter selection, carve it from the TRAIN split using GroupKFold on cluster_id; never touch cal or test.
4. Handle class imbalance without synthetic oversampling: use weights="distance", tune the decision threshold on cal, and report balanced accuracy.

MODEL SPECIFICS:
- Use sklearn KNeighborsClassifier with metric suited to binary data: try both "hamming" and "jaccard" (algorithm="brute"). Sweep n_neighbors in {1,3,5,7,11,15} and weights in {uniform, distance}, selecting via GroupKFold on cluster_id within TRAIN.
- Calibrate the selected model's probabilities with CalibratedClassifierCV(cv="prefit") fit on CAL; compare method="isotonic" and method="sigmoid" and keep the better Brier on cal.
- Implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6. ADDITIONALLY, compute each test genome's mean distance to its k nearest TRAIN neighbors and route out-of-distribution genomes (distance beyond the 95th percentile of cal distances) to "no-call" — this uses distance-to-neighbors as an OOD signal.

REPORTING:
- On the TEST split, report per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and a reliability diagram (plot calibration curve). Also report no-call rate and accuracy-on-called.
- Report metrics broken down PER GENETIC GROUP, explicitly separating test clusters that were SEEN vs UNSEEN in training, and print the expected performance drop on unseen clusters.
- Because this is a clonality negative control, also report the distribution of distance-to-nearest-train-neighbor and how much accuracy is concentrated among low-distance (same-lineage) test genomes.
- Save per-antibiotic metrics to a dict and dump to JSON, then print a summary table across antibiotics.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate any data. Present neighbor votes as statistical association only, never as biological causation. Output one self-contained script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
