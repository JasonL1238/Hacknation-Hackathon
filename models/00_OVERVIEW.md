# Focused Model Research Set

This folder now contains only models that Genome Firewall currently uses or has a clear
next experiment for. It is deliberately not a menu of every possible classifier.

Run local checks and organize new outputs in
[`experiments/model_bakeoff/`](../experiments/model_bakeoff/README.md).

## Current data and evaluation contract

Every research model must use the same files:

- `data/processed/features.parquet`: AMRFinder gene/mutation features (`X`).
- `data/processed/labels.csv`: observed per-antibiotic R/S outcomes (`y`).
- `data/processed/splits.json`: fixed Mash `train`/`cal`/`test`, broader `cluster_id`,
  and strict `dedup_group_id`.
- `db/drugs_saureus.csv`: catalog markers and target-gate reference.

The binding protocol is:

1. Keep every Mash cluster and duplicate family inside one split.
2. Tune only with `StratifiedGroupKFold(cluster_id)` inside `train`.
3. Give each labeled member of a strict duplicate family weight
   `1 / labeled family size`; each family therefore contributes about one vote.
4. Fit the supervised model on `train`, probability calibration on `cal`, and evaluate
   `test` once.
5. Report ordinary and duplicate-weighted Brier, balanced accuracy, recall R/S, F1,
   AUROC, PR-AUC, no-call rate, accuracy-on-called, reliability, and per-cluster results.
6. Never select a model, feature setup, threshold, or hyperparameter from test results.

The current test set has already been inspected. New candidates must be selected using
grouped train OOF evidence and require new external data for a fresh unbiased final claim.

## Models retained

| File | Role | Status |
|---|---|---|
| [01](01_logistic_regression_l2.md) | L2 logistic reference | tested |
| [02](02_logistic_regression_l1_elasticnet.md) | L1 member of completed ensemble; Elastic Net candidate | L1 tested / Elastic Net next |
| [08](08_hist_gradient_boosting.md) | nonlinear tree learner in completed ensemble | tested |
| [09](09_xgboost.md) | current genotype-only production learner | deployed refit |
| [13](13_tabpfn.md) | small-tabular foundation-model challenger | next candidate |
| [14](14_explainable_boosting_machine.md) | interpretable pairwise-interaction challenger | next candidate |
| [23](23_soft_voting_ensemble.md) | record and implementation guide for the completed ensemble | tested / not universal winner |

## What to do next

Do not rerun the entire catalog. The next comparison is limited to:

1. Elastic Net from file 02.
2. Explainable Boosting Machine from file 14.
3. TabPFN from file 13, only if the installed API can honor duplicate-family training
   weights; otherwise record it as incompatible and skip it.

Compare these against the existing L2, HGB, and XGBoost references using duplicate-weighted
grouped train OOF Brier. The completed soft ensemble remains a result for comparison, not
the default deployment choice.

> Research prototype—confirm every result with standard laboratory testing; a trained
> professional makes the decision.
