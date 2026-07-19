# Duplicate-Aware Genotype Soft Ensemble

## Current status

This completed local experiment uses only the AMRFinder genotype feature matrix. It fits
L1 logistic regression, HistGradientBoosting, XGBoost, and a probability-level soft
ensemble for each antibiotic.

The retained run used `--voting inverse-brier`. Voting weights were learned separately
per antibiotic from duplicate-weighted grouped train-OOF Brier and never from test. The
ensemble had the best held-out weighted Brier only for gentamicin, so it is an experiment
and implementation record—not the universal default.

## Duplicate and leakage policy

- Use the committed whole-genome Mash split in `data/processed/splits.json`.
- No `cluster_id` or strict `dedup_group_id` may cross train/cal/test.
- Keep all genomes, but give each labeled member of a duplicate family weight
  `1 / labeled family size`.
- Tune model hyperparameters with stratified grouped folds inside train only.
- Fit probability calibration on cal only and evaluate test once.
- Report ordinary and duplicate-weighted metrics plus per-cluster results.

## Inputs

```text
data/processed/features.parquet
data/processed/labels.csv
data/processed/splits.json
db/drugs_saureus.csv
```

## Command

```bash
conda activate genome-firewall
PYTHONPATH=src python -m genome_firewall.model_ensemble \
  --setups genotype_only \
  --voting inverse-brier
```

## Outputs

Everything is written under `reports/soft_ensemble/`:

- `model_comparison.csv`: every antibiotic × model with ordinary and weighted metrics.
- `selected_feature_setup.csv`: train-OOF-selected setup; genotype-only in this project.
- `train_oof_feature_comparison.csv`: grouped train-OOF selection evidence.
- `test_predictions.csv`: calibrated probabilities and no-call flags.
- `per_cluster_metrics.csv`: held-out Mash-cluster performance.
- `oof_model_disagreement.csv`: base-model diversity and probability correlation.
- `l1_coefficients.csv`: statistical-only L1 associations.
- `reliability_<antibiotic>.png`: reliability plots.
- `run_config.json`: exact paths and settings.

Fitted artifacts are written under `data/processed/ensemble_models/`.

Do not declare the ensemble the winner unless it beats the simpler base learners using a
selection rule fixed before viewing test. The current test has already been inspected, so
new model selection requires grouped train OOF evidence and external validation.

> Research prototype—confirm every result with standard laboratory testing; a trained
> professional makes the decision.
