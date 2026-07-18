# Conformal Prediction (split / Mondrian) for principled no-call

> **One-liner:** A distribution-free wrapper that turns any base model into set-valued predictions with a coverage guarantee, giving a principled, statistically-grounded no-call.
> **Category:** method ·
> **Runs on:** local CPU ·
> **Priority:** recommended ·
> **Interpretable:** partial (the guarantee and set size are transparent; the base model's evidence still needs its own explainer)

## Why it fits Genome Firewall
Two of the judged priorities — honest no-call and calibrated confidence — line up almost exactly with what conformal prediction delivers. Instead of forcing a single R/S label, split (inductive) conformal produces a **prediction set** for each genome with a finite-sample coverage guarantee (e.g. the true label is inside the set at least 90% of the time), using the dedicated `cal` split as the conformal calibration set. On this small, imbalanced, per-antibiotic *S. aureus* problem that maps cleanly onto our three outcomes: a confident singleton, or an honest no-call when the evidence is weak or contradictory. It wraps **any** base model in this folder, so it composes with the calibrated probabilities we already produce rather than replacing them.

## When to prefer it / when to skip it
Prefer conformal prediction when you want a *guaranteed* no-call rate rather than a hand-tuned ambiguity band — it is the most defensible way to justify no-calls to a skeptical judge, because the coverage level is chosen up front and verified empirically on test. Use **Mondrian (class-conditional) conformal** rather than plain split conformal here, because the classes are imbalanced: class-conditional calibration guarantees coverage *separately* for R and S, so the rare class is not silently under-covered. Skip it, or treat it as a secondary reporting layer, when the simple calibrated-probability + 0.4–0.6 band already meets the no-call goals and you want to keep the pipeline minimal; the two approaches can also be reported side by side. It does not improve raw discrimination — it is about honest abstention, not accuracy.

## Data interface (the contract this code must respect)
- Wraps a base classifier already fit on the **train** split ONLY (any model in this folder).
- Uses the **`cal`** split from `data/processed/splits.json` as the **conformal calibration set** — computing nonconformity scores there, never on train or test.
- Reports empirical coverage, average set size, and the resulting verdict distribution on the **`test`** split ONLY, and per `cluster_id` genetic group.
- Runs **per antibiotic**, aligned with the per-antibiotic base models; reads `db/drugs_saureus.csv` for the target gate.

## Adversarial checks it must survive
- **No leakage (Rule 1):** the coverage guarantee assumes the conformal calibration set is exchangeable with test and disjoint from what the base model trained on. Use the grouped `cal` split verbatim and confirm no `cluster_id` is shared with the base model's train set — a leaked cluster invalidates the guarantee.
- **Grouped exchangeability caveat:** standard split conformal assumes exchangeable examples, but *S. aureus* is clonal and our data is grouped by cluster, so the i.i.d. assumption is only approximate. State this honestly, report empirical coverage per genetic group (including unseen clusters), and expect coverage to degrade on clusters unlike anything in `cal` — that degradation is itself an honest OOD signal, not a bug to hide.
- **Class imbalance (Rule 3):** plain split conformal can meet marginal coverage while under-covering the rare class; use Mondrian / class-conditional conformal so R and S are each covered at the target level.
- **Honest no-call (Rule 3):** map an empty set (nothing plausible) OR a both-classes set `{R,S}` (both plausible) to **no-call**; only a singleton is a confident call. Never collapse an ambiguous set into a forced label.
- **Target gate (Rule 4):** even a singleton `{S}` must pass the deterministic target gate — if the drug's target genes are absent, do not upgrade to "likely to work" from marker absence alone.
- **Not an explainer (Rule 5):** the set and its coverage are statistical; the biological evidence (genes/mutations) still comes from the base model's explainer, and set membership is not causal proof.

## Hyperparameters worth sweeping
- **Target error rate `alpha`** (miscoverage): e.g. 0.05, 0.10, 0.20 — trades set size / no-call rate against coverage; report the full trade-off curve.
- **Nonconformity score:** `1 - p_true` (least-ambiguous / LAC) vs adaptive scores (APS / RAPS) — APS/RAPS tend to give more stable set sizes on imbalanced data.
- **Conditional scheme:** marginal split conformal vs **Mondrian / class-conditional** (recommended) vs cluster-conditional if enough support exists.
- **Base-model probability source:** raw vs calibrated `predict_proba` fed into the nonconformity score (calibrated scores usually give tighter, more stable sets).

## Calibration & no-call handling
Conformal prediction *is* the no-call mechanism here, layered on top of (not instead of) the calibrated probabilities. Fit the base model on `train`, calibrate it on `cal` (see the calibration-methods file), then either reserve a portion of `cal` for the conformal step or use the same `cal` split to compute class-conditional nonconformity scores; at inference, form the prediction set at level `alpha`. Decision map: singleton `{R}` or `{S}` → confident call at that verdict; empty set or `{R,S}` → **no-call**. This can be reported alongside the probability-band no-call so the two abstention mechanisms can be compared. Libraries: **MAPIE** (`MapieClassifier` with `method="lac"|"aps"|"raps"`, class-conditional option) or **crepes** — both wrap an sklearn-style base model directly.

## Metrics to report
On the held-out grouped **test** split, and per genetic group (including unseen clusters): **empirical coverage** (marginal and per class) vs the target `1 - alpha`, **average prediction-set size**, and the resulting **no-call rate + accuracy-on-called** derived from the singleton/empty/both-classes mapping. Also report the standard set alongside it: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, and the **reliability diagram** of the underlying calibrated probabilities. Expect and report a coverage drop on unseen clusters.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable conformal-prediction code for this project.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible), with a CALIBRATED confidence and a principled NO-CALL. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) and HONEST ABSTENTION over raw accuracy.

Write complete, runnable Python that adds CONFORMAL PREDICTION on top of a base classifier to produce set-valued predictions with a coverage guarantee and a principled no-call. Use MAPIE (MapieClassifier) or crepes; if unavailable, implement split/inductive conformal by hand. Run one conformal wrapper per antibiotic.

DATA CONTRACT (files already exist on disk):
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split by genetic cluster: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are entirely unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.

PROTOCOL (obey exactly):
1. For each antibiotic, fit a base classifier (use sklearn LogisticRegression(class_weight="balanced") as the base model) on the TRAIN split ONLY. Map label R->1, S->0.
2. Use the CAL split as the CONFORMAL CALIBRATION set — compute nonconformity scores there ONLY. Report ALL metrics on the TEST split ONLY. NEVER use train or test to calibrate the conformal scores.
3. NEVER re-split randomly and NEVER let a cluster span splits — always use splits.json.
4. Because classes are IMBALANCED, use MONDRIAN / CLASS-CONDITIONAL conformal so R and S are each covered at the target level (not just marginal coverage). Try nonconformity scores "lac" and "aps"/"raps". Sweep target error alpha in {0.05, 0.10, 0.20}.
5. Map prediction sets to verdicts: a singleton {R} or {S} -> confident call; an EMPTY set OR a both-classes {R,S} set -> NO-CALL. Also expose a target-gate hook: if the drug's target_genes are all absent in a genome, do not output "likely to work" from marker absence alone, even for a singleton {S}.

IMPORTANT honesty note to encode in comments: standard conformal assumes exchangeability, but this data is grouped by genetic cluster (S. aureus is clonal), so the guarantee is only approximate on unseen clusters — report per-cluster coverage and treat coverage degradation on unseen clusters as an OOD signal.

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id) including clusters unseen in training, compute: empirical coverage (marginal AND per class) vs target 1-alpha, average prediction-set size, and no-call rate + accuracy-on-called from the singleton/empty/both mapping. Also report balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score of the underlying calibrated probabilities, and plot a reliability diagram per antibiotic.
- Save per-antibiotic, per-alpha metrics to a dict and to JSON (e.g. reports/metrics_conformal.json) and print a summary table (rows = antibiotic x alpha, columns = the metrics above).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
