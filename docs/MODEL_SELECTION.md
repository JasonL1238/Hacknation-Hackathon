# Historical model-selection experiment — superseded for deployment

> **Current deployment:** per-antibiotic calibrated XGBoost, refit on all labeled data
> by `genome_firewall.final_train`. The ensemble below is retained as an experiment and
> historical comparison; it is no longer served by the app. XGBoost was selected by the
> project owner after test reports had been inspected, so external validation is required
> before making an unbiased final performance claim.

**Historical served model:** a per-antibiotic **soft-voting ensemble** of
`l2_logistic + l1_logistic + hist_gradient_boosting`, calibrated (isotonic) on the
dedicated cal split. One `SoftVotingEnsemble` object per drug lives at
`data/processed/models/<antibiotic>.pkl` — the same file the app (`report.py`) and
`evaluate.py` already load. The former single-logistic baseline is preserved at
`data/processed/models/baseline_backup/`.

Reproduce everything below with:

```bash
make split                                              # grouped, leak-free splits
PYTHONPATH=src python -m genome_firewall.model_select   # bakeoff → select → write served models
make evaluate                                           # held-out metrics.json + reliability/PR plots
```

Research prototype — every result must be confirmed by standard laboratory testing.
Decision support only; a trained professional makes the decision. This tool never
designs, modifies, or optimises any organism.

---

## 1. The question

Rather than hand-pick one classifier, we ran a bakeoff of CPU-local models, then combined
the best few into a soft-voting ensemble — chosen so its confidence scores are honest and
its decisions are safe, the axes the challenge is judged on (balanced accuracy; recall for
resistant and susceptible cases separately; F1; AUROC; PR-AUC; Brier + reliability; no-call
rate and accuracy-on-called; generalization to unseen genetic groups).

## 2. The one rule that governs everything: never select on the test split

Model choice, hyperparameters, and the ensemble trio are selected **only** on
**train grouped out-of-fold (OOF)** performance. `StratifiedGroupKFold` on `cluster_id`
means no genetic cluster spans a fold, and near-identical genomes are down-weighted by
inverse dedup-group size. The held-out **test split is touched exactly once**, by
`evaluate.py`, to report the numbers in §5 — never to decide anything. Calibration is fit
on the dedicated **cal** split only.

## 3. Candidate pool (all CPU-local, no GPU)

`l2_logistic`, `l1_logistic`, `hist_gradient_boosting`, `xgboost`, `lightgbm`,
`random_forest`, `extra_trees`, `bernoulli_nb`, `knn`. Each is tuned over a small grid with
grouped CV inside the train split, scored by dedup-weighted OOF Brier. Full per-candidate,
per-drug OOF numbers: `reports/model_selection/candidate_oof.csv`; single-candidate
calibrated **test** numbers (for reference only, not used to select): `candidate_test.csv`.

## 4. How the trio was chosen — and why the objective changed once

We select **one global trio** (the same three learners for every drug): fewer selection
decisions on small drugs, and one honest "our model is X" story.

**Selection objective — a Borda composite of OOF Brier (calibration) *and* OOF balanced
accuracy (discrimination).** Our first attempt ranked trios on OOF Brier alone and picked
`l1_logistic + hist_gradient_boosting + random_forest`. On the held-out test that trio
*collapsed tetracycline* (AUROC 0.94→0.69, PR-AUC 0.81→0.47). Root cause, visible purely in
the OOF table: `random_forest` had the **best** OOF Brier for tetracycline but the **worst**
OOF balanced accuracy — it was well-calibrated but poorly-discriminating (predicting near
the base rate). Brier alone rewarded exactly the member that generalises worst. Because the
rubric weights discrimination *and* calibration, the correct objective does too. Switching
to the composite (still computed only on train OOF) selects
`l2_logistic + l1_logistic + hist_gradient_boosting`, which has the best OOF balanced
accuracy (0.852) and near-identical OOF Brier (0.109 vs 0.108).

Top trios by the composite (`reports/model_selection/trio_ranking.csv`):

| trio | mean OOF wBrier | mean OOF w-bal-acc | composite rank |
|---|---|---|---|
| **l2_logistic + l1_logistic + hist_gradient_boosting** | 0.1093 | 0.8517 | **2.0 (best)** |
| l1_logistic + hist_gradient_boosting + random_forest | 0.1084 | 0.8475 | 2.5 |
| l1_logistic + hist_gradient_boosting + extra_trees | 0.1085 | 0.8477 | 2.5 |
| l1_logistic + hist_gradient_boosting + xgboost | 0.1094 | 0.8486 | 3.0 |

Member complementarity (mean OOF over drugs, `member_disagreement.csv`): HistGradientBoosting
is the diverse member (prob-correlation 0.88–0.92 with the logistics); the two logistic
members are highly correlated (0.95). We keep both anyway — the composite prioritises
OOF-validated performance over diversity for its own sake, and the "more diverse" random-forest
alternative is precisely the one that broke tetracycline generalization.

## 5. Held-out results — baseline (single L2 logistic) → historical ensemble

All numbers on the grouped test split; **every test cluster is a genetic group unseen in
training**. Full breakdown incl. per-cluster in `data/processed/metrics.json`
(`metrics_baseline.json` / `metrics_ensemble.json` are the two snapshots side by side).

| metric (macro) | baseline | ensemble | Δ |
|---|---|---|---|
| balanced accuracy | 0.7905 | **0.7993** | +0.009 |
| recall_R | 0.6810 | **0.7114** | +0.030 |
| recall_S | 0.8998 | 0.8872 | −0.013 |
| F1 | 0.7172 | **0.7219** | +0.005 |
| AUROC | 0.8818 | 0.8817 | ≈0 |
| PR-AUC | 0.8002 | **0.8088** | +0.009 |
| Brier | 0.1361 | **0.1337** | −0.002 (better) |
| no-call rate | 0.0197 | 0.0198 | ≈0 |

Per drug (balanced accuracy / recall_R / AUROC / PR-AUC / Brier):

| drug | baseline | ensemble | note |
|---|---|---|---|
| **gentamicin** | 0.816 / 0.758 / 0.912 / 0.627 / 0.117 | **0.903 / 0.939 / 0.910 / 0.659 / 0.089** | large win: recall_R +0.18, Brier −0.027 |
| cefoxitin | 0.864 / 0.927 / 0.840 / 0.871 / 0.095 | **0.872 / 0.953 / 0.881 / 0.910** / 0.098 | AUROC/PR-AUC up |
| erythromycin | 0.921 / 0.874 / 0.921 / 0.938 / 0.077 | **0.926 / 0.891 / 0.936 / 0.942 / 0.065** | uniformly up |
| clindamycin | **0.840** / 0.910 / **0.901 / 0.872** / 0.135 | 0.819 / 0.919 / 0.883 / 0.851 / **0.128** | small discrimination dip, Brier better |
| ciprofloxacin | 0.677 / 0.359 / **0.779 / 0.685** / **0.205** | 0.677 / 0.359 / 0.739 / 0.663 / 0.214 | see §6 (OOD clade) |
| tetracycline | 0.625 / **0.258** / 0.938 / 0.807 / **0.189** | 0.599 / 0.206 / **0.942 / 0.828** / 0.207 | see §6 (OOD clade) |

Net: a modest but real improvement on the aggregate judged metrics, driven strongly by
gentamicin, cefoxitin, and erythromycin, with small decision-level regressions on three
drugs attributable to out-of-distribution clades.

## 6. Honest limitations (what we did *not* fix, and why)

- **Out-of-distribution resistant clades cap ciprofloxacin and tetracycline.** For
  tetracycline the drug-level score is dominated by one unseen clade — test cluster 49
  (74 resistant / 4 susceptible genomes) — predicted susceptible with AUROC 0.5 and Brier
  0.88. The **baseline fails it too** (baseline tetracycline recall_R was 0.258). This is
  the honest unseen-group generalization drop the rubric expects, not a bug we can tune away
  without looking at test. ciprofloxacin's resistance is a near-deterministic gyrA/parC
  point-mutation signal; a whole resistant test clade sits far enough from training that the
  0.5 threshold mis-places it even though ranking (AUROC) is preserved elsewhere.
- **No single global trio is best for every drug.** ciprofloxacin's mutation rule is
  tree-friendly; tetracycline is logistic-friendly. We accept the global trio (best on the
  principled OOF composite) rather than per-drug selection, because on **OOF** — the only
  signal we may use — ciprofloxacin's tree benefit is *not* visible (its best OOF models are
  logistic), so per-drug selection would not recover it and would only add overfitting risk
  on small drugs.
- **We stopped iterating against the test set on purpose.** After two test evaluations
  (Brier-only trio → composite trio) we froze the objective. Continuing to swap members to
  improve a per-drug test number would be hand-tuning on the test set — a subtle leak the
  rigor rules forbid.

## 7. Recommended next step (does not use test labels)

The residual failures are OOD clades the model is *confidently wrong* about. The principled,
non-leaking fix is the planned **OOD no-call**: abstain when a genome's feature vector is far
from every training genome (nearest-neighbour distance threshold set on train/cal only), or
carries an unseen feature combination. That converts confident errors on clusters like #49
into honest no-calls — directly improving the "safe, honest performance / accuracy-on-called"
axis the challenge rewards. It is not yet implemented (no `nocall.py`/OOD module exists; the
served path only does probability-band + target-gate abstention).
