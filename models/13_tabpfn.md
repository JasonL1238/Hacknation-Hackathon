# TabPFN

> **One-liner:** A pretrained transformer that performs in-context Bayesian-style classification on small tabular datasets with no gradient training at fit time.
> **Category:** tabular-DL (foundation model) ·
> **Runs on:** local CPU/GPU ·
> **Priority:** recommended ·
> **Interpretable:** no

## Why it fits Genome Firewall
Each antibiotic gives a small, imbalanced tabular problem — hundreds-to-low-thousands of genomes described by tens-to-low-hundreds of sparse binary features — which is precisely the regime TabPFN was pretrained for. It "trains" by conditioning on the training rows in a single forward pass, so it is near-instant per antibiotic and requires essentially no hyperparameter tuning. Most importantly for this project, TabPFN tends to produce **well-calibrated probabilities out of the box**, which directly serves the judged priority (Brier score + reliability) and the downstream no-call band.

## When to prefer it / when to skip it
Prefer TabPFN when the per-antibiotic dataset fits inside its sample/feature limits and you want strong, honest calibration with almost zero tuning effort — it is a strong default on the calibration axis. Skip or adapt it when a dataset exceeds the current version's caps (subsample rows / select features first) or when you need feature-level interpretability, since TabPFN is a black box and cannot itself justify which gene drove a call (use logistic regression or the catalog/target-gate for explanations). It complements, rather than replaces, an interpretable core model.

## Data interface (the contract this code must respect)
- Read `data/processed/features.parquet` (index `genome_id`, int8 binary columns) as X.
- Read `data/processed/labels.csv`; per antibiotic build the R/S target aligned to feature rows.
- Read `data/processed/splits.json` for `train` / `cal` / `test` assignment and `cluster_id`.
- Condition (fit) on the **train** split ONLY. Assess/adjust calibration on **cal** ONLY. Report metrics on **test** ONLY.
- Check the installed TabPFN version's documented sample and feature limits; if train exceeds them, subsample training rows (respecting clusters — never split a cluster) or select the top features, and record what was dropped.

## Adversarial checks it must survive
- **Leakage (rule 1):** only the train split rows may be passed as the in-context training set; `cal` and `test` genomes must never appear in the context. Because it is grouped by cluster, verify no `cluster_id` leaks into the context set.
- **Calibration (rule 2):** TabPFN is usually well-calibrated, but do NOT assume it — measure Brier + reliability on `test`. If reliability drifts, add a light temperature-scaling / Platt step fit on `cal` and keep whichever gives the lower cal Brier. Never tune calibration on test.
- **Honest no-call (rule 3):** feed calibrated p into the ambiguous band and route uncertain genomes to `no-call`; do not force a call to look decisive.
- **Honest explanation (rule 5):** TabPFN gives no per-feature attribution you can trust as causal. Supporting genes/mutations shown to users must come from the AMR catalog and target gate, not from post-hoc importance on TabPFN.
- **Generalization (rule 6):** report per-genetic-group metrics including unseen clusters and expect a drop; a foundation model does not exempt you from this.
- **Sample/feature caps:** if you subsampled to fit limits, treat that as a modeling decision to justify — report how many rows/features were dropped and check results are stable to the choice.

## Hyperparameters worth sweeping
There is deliberately almost nothing to sweep — that is a selling point. The main knobs:
- Ensembling: `N_ensemble_configurations` (TabPFN v1) or the v2 equivalent number of estimators — more ensemble members can improve calibration/stability at some compute cost.
- Device: CPU vs GPU (`device="cpu"|"cuda"`) — performance only, not model quality.
- Preprocessing for the row/feature caps: subsample size and feature-selection count if you exceed limits.
Verify the exact knobs and the current sample/feature limits against your installed **TabPFN v2** documentation before running.

## Calibration & no-call handling
Obtain probabilities from TabPFN conditioned on train, then verify calibration on `cal` via a reliability curve and Brier score. If already well-calibrated, use the probabilities directly; otherwise fit a single temperature (or sigmoid) on `cal` and apply it. Feed the final calibrated p into the no-call logic: ambiguous band (~0.4–0.6) → `no-call`, plus the pipeline's OOD and target-gate no-calls. Report the no-call rate and accuracy-on-called on `test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called — on the held-out grouped **test** split and per genetic group (including unseen clusters). Model-specific: report calibration both before and after any temperature step so the "calibrated out of the box" claim is evidenced, not assumed.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S) to that antibiotic, with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION quality (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

Write complete, runnable Python that uses TabPFN (the pretrained tabular foundation model) to classify small per-antibiotic datasets. TabPFN needs no gradient training and tends to be well-calibrated out of the box, which is why it fits this calibration-first project.

DATA CONTRACT (assume these files exist, paths as given):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Union of columns across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant / likely-to-fail, S = susceptible / likely-to-work), source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

PROTOCOL (obey exactly):
1. Train one model PER antibiotic (loop over antibiotics in labels.csv).
2. Condition (fit) TabPFN on the TRAIN split ONLY. Assess/adjust probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster_id span splits — always use splits.json. Never place cal or test genomes into TabPFN's in-context training set.
4. Handle class imbalance honestly (report balanced accuracy, recall_R, recall_S); do NOT use synthetic oversampling.

MODEL SPECIFICS:
- Use the TabPFN classifier (import from the tabpfn package). FIRST check the installed TabPFN v2 documented limits on number of samples and number of features. If the TRAIN split exceeds them, subsample training rows WITHOUT splitting any cluster_id, or select the top-k most informative binary features, and print exactly how many rows/features were dropped.
- The main tunable is ensembling (N_ensemble_configurations in v1 or the v2 equivalent number of estimators); there is otherwise deliberately no hyperparameter sweep. Allow device="cpu" or "cuda".
- After getting TabPFN probabilities, VERIFY calibration on CAL with a reliability curve and Brier score. If poorly calibrated, fit a single temperature (or sigmoid) on CAL and apply it; keep whichever gives lower CAL Brier. Never tune calibration on test.
- Implement a no-call rule: return "no-call" when calibrated p is in the ambiguous band ~0.4-0.6 (the pipeline also has OOD and target-gate no-calls, which you can stub as hooks).

REPORTING:
- On the TEST split, report per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and a reliability diagram. Also report no-call rate and accuracy-on-called.
- Report metrics broken down PER GENETIC GROUP, explicitly separating test clusters SEEN vs UNSEEN in training, and print the performance drop on unseen clusters.
- Report calibration (Brier + reliability) BOTH before and after any temperature step, to evidence the "calibrated out of the box" claim rather than assume it.
- Save per-antibiotic metrics to a dict and dump to JSON, then print a summary table across antibiotics.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate any data. TabPFN gives no trustworthy causal feature attribution, so do not present any importance as biological causation. Output one self-contained script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
