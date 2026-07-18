# RBF-Kernel Support Vector Machine

> **One-liner:** A nonlinear kernel classifier that scores genomes by similarity in an implicit high-dimensional space, able to capture gene-combination effects but prone to overfitting small imbalanced data.
> **Category:** kernel ·
> **Runs on:** local CPU ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
Some resistance phenotypes may depend on **combinations** of genes rather than any single marker (e.g. a target mutation only matters alongside an efflux gene), and an RBF kernel can, in principle, model those nonlinear interactions that a linear model misses. Including it lets the project honestly claim it tested for nonlinearity rather than assuming linearity. That said, the value here is diligence, not a expected win — on a small, imbalanced, clonally structured dataset it usually cannot beat the linear baseline.

## When to prefer it / when to skip it
Treat this as a **stretch experiment to prove nonlinearity was tested**, not a production candidate. Only prefer it if it beats the L2 baseline (file 01) on the held-out grouped-test **Brier score** AND that advantage survives the per-genetic-group breakdown (including unseen clusters) — a bar it will rarely clear. Skip it as the deployed model when data is small/imbalanced (the common case here): it overfits, calibrates poorly, and is uninterpretable, all of which cut against the judged priorities. Frame its likely result honestly in the writeup: included for rigor, expected not to win.

## Data interface (the contract this code must respect)
- Reads `data/processed/features.parquet` (index `genome_id`, binary int8 columns) as X.
- Reads `data/processed/labels.csv`, filtered per antibiotic; maps R→1, S→0.
- Reads `data/processed/splits.json` for grouped train/cal/test and `cluster_id`; never re-split randomly.
- Fit on **train** only; calibrate on **cal** only; report metrics on **test** only.
- Reads `db/drugs_saureus.csv` for the downstream target gate.

## Adversarial checks it must survive
- **Clonal memorization (the big risk):** An RBF kernel measures genome-to-genome similarity, so it can effectively memorize training lineages and score by "which known clone is this closest to" rather than by mechanism — which inflates in-distribution scores and collapses on unseen clusters. Mitigation: report per-genetic-group metrics with emphasis on **unseen clusters**, and expect a large drop there; tune `gamma` to avoid a too-local kernel.
- **Overfitting small imbalanced data:** With few genomes per antibiotic, a flexible kernel overfits. Mitigate with strong regularization (small `C`), careful `gamma`, and `class_weight="balanced"`.
- **Poor calibration (Rule 2):** Kernel SVM scores are especially poorly calibrated; never trust raw scores. Calibrate on `cal` and report Brier + reliability on `test` — and be prepared to report that calibration only partly fixes it.
- **No native probabilities:** As with the linear SVM, do NOT use `SVC(probability=True)`'s internal CV (not grouped-aware, leaks clonal structure). Fit `SVC(kernel="rbf", probability=False)` on train, then wrap in `CalibratedClassifierCV(cv="prefit")` on `cal`.
- **No leakage (Rule 1):** Use `splits.json` verbatim; sweep `C`/`gamma` with GroupKFold on `cluster_id` inside train only.
- **No interpretability (Rule 5):** There is no honest per-gene explanation from the kernel; do not manufacture one. State plainly that this model cannot supply the gene-level evidence the report requires — a further reason it is a stretch, not the deployed model.

## Hyperparameters worth sweeping
- `C` (regularization): logspace `1e-2 … 1e2` — lean toward smaller C to fight overfitting.
- `gamma` (kernel width): `"scale"`, `"auto"`, and an explicit logspace `1e-3 … 1e0`; small gamma = smoother/less-local, which resists clonal memorization.
- `class_weight="balanced"`.
- Calibration `method`: `"sigmoid"` (safer on small cal) vs `"isotonic"`.
- Select over the `(C, gamma)` grid with GroupKFold on `cluster_id` **within train only**, scoring by Brier.

## Calibration & no-call handling
Fit `SVC(kernel="rbf", class_weight="balanced", probability=False)` on train, then `CalibratedClassifierCV(estimator=fitted, cv="prefit", method=...)` on the **cal** split — expect calibration to be necessary and still imperfect. The calibrated probability feeds the no-call band (~0.4–0.6). Because this model is likely to be over-confident and OOD-fragile, lean on the OOD check to route unseen-cluster genomes to `no-call`, and enforce the target gate (drug target absent → no "likely to work" from marker absence alone).

## Metrics to report
On held-out grouped **test**, and **per genetic group** (including unseen clusters): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, no-call rate + accuracy-on-called. Model-specific note: highlight the in-distribution vs unseen-cluster gap (the clonal-memorization test) and report the headline metrics as a **delta versus the L2 baseline (file 01)** — the honest expected outcome is no improvement.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy. This model is a STRETCH experiment to test for nonlinearity; it is expected NOT to beat a linear baseline, and that honest result is fine.

Write complete, runnable Python (scikit-learn, pandas, numpy, matplotlib) that trains an RBF-KERNEL SVM. It has no native probabilities, so it MUST be calibrated on the cal split.

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

MODEL SPECIFICS:
- Use sklearn.svm.SVC(kernel="rbf", class_weight="balanced", probability=False) as the base estimator. Do NOT use probability=True (its internal CV is not aware of our grouped split and can leak clonal structure).
- Fit the base SVM on train, then wrap the FITTED estimator in CalibratedClassifierCV(cv="prefit", method=...) and fit that on the CAL split. Compare method="sigmoid" and "isotonic"; pick per antibiotic by cal-split Brier.
- Sweep C in np.logspace(-2, 2, 8) and gamma in {"scale","auto"} plus np.logspace(-3, 0, 6), via GroupKFold(cluster_id) on the train split only, scoring by Brier. Prefer smaller C and smaller gamma to resist overfitting and clonal memorization.
- This model is NOT interpretable: do not fabricate a per-gene explanation. State in the output that it cannot supply gene-level evidence.

OUTPUT / METRICS:
- On the TEST split, and PER genetic group (cluster_id) including unseen clusters, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score (on calibrated probabilities), no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic. Explicitly report the in-distribution vs unseen-cluster performance gap to expose clonal memorization.
- Save per-antibiotic metrics to a dict and to JSON (e.g. reports/metrics_rbf_svm.json).
- Print a clean summary table (rows = antibiotics, columns = the metrics above).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
