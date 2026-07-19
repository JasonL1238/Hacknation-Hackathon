# Explainable Boosting Machine

> **Role:** next candidate · **Runs on:** local CPU · **Interpretable:** yes, statistical only

## Why test it

An Explainable Boosting Machine (EBM) is a generalized additive model that can include a
small number of pairwise feature interactions. It is a useful middle ground between a
linear model and XGBoost: it can test combinations such as two co-occurring AMR markers
without turning every prediction into an opaque tree ensemble.

## Duplicate-aware data contract

- Read `features.parquet`, `labels.csv`, and the committed Mash `splits.json`.
- Train one EBM per antibiotic.
- Assert that neither `cluster_id` nor `dedup_group_id` spans train/cal/test.
- Within each antibiotic and fitting subset, set each row's sample weight to
  `1 / labeled dedup-group size`, then normalize weights to mean one.
- Tune only with stratified grouped folds by `cluster_id` inside train.
- Fit the final EBM on train, fit a sigmoid/Platt calibrator on cal, and evaluate test once.
- Do not use SMOTE, random row splits, test-selected interactions, or test-selected
  hyperparameters.

## Fixed first experiment

Use `interpret.glassbox.ExplainableBoostingClassifier` and compare these train-OOF
configurations:

- interactions: `0`, `5`, `10`
- learning rate: `0.01`, `0.03`, `0.05`
- minimum samples per leaf: `5`, `10`, `20`
- outer bags: `8`
- inner bags: `0`
- random seed: `42`

Select the configuration with the lowest duplicate-weighted grouped-OOF Brier; use
weighted balanced accuracy only as a tie-break. Record the selected main effects and
interactions as statistical associations, never biological causation.

## Required outputs

For every antibiotic, save:

- grouped train-OOF selection table;
- calibrated held-out test predictions;
- ordinary and duplicate-weighted headline metrics;
- per-Mash-cluster metrics and reliability plot;
- global main effects and selected pairwise interactions;
- deltas versus L2, L1, HGB, and XGBoost on the same split.

Because the current test set has already been viewed, use train OOF to decide whether EBM
is promising. A new external holdout is required before claiming that it improves the
final model.

> Research prototype—confirm every result with standard laboratory testing; a trained
> professional makes the decision.
