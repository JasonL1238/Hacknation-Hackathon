# Duplicate-Aware Soft Ensemble

This plan is implemented in `src/genome_firewall/model_ensemble.py`. You no longer need
to paste this file into ChatGPT to generate a new notebook.

## What it trains

For each antibiotic and each available feature setup, the trainer fits:

1. L1 logistic regression
2. HistGradientBoosting
3. XGBoost
4. A soft ensemble that averages the three P(Resistant) values

The average is calibrated once on the dedicated calibration split. Sigmoid/Platt
calibration is the preselected default because some antibiotic calibration subsets are
small. The held-out test set is evaluated once and is never used to tune models, voting
weights, calibration, or feature setup.

## Duplicate and leakage policy

- `make split` uses whole-genome Mash distances when Mash and raw FASTAs are available.
- Every genome receives both a broader `cluster_id` and a stricter `dedup_group_id`.
- No cluster or duplicate group may cross train/cal/test.
- All genomes are retained. For each antibiotic, a dedup family of size `n` gives each
  labeled member weight `1/n`; the family therefore contributes approximately one vote.
- Hyperparameters are selected with stratified grouped folds inside train only.
- Both ordinary genome-level and duplicate-weighted test metrics are reported.
- Feature setup is selected by duplicate-weighted grouped-OOF Brier score inside train,
  with weighted balanced accuracy only as a tie-break. Test results do not select it.

## Input paths

Always required after cloning:

```text
data/processed/features.parquet
data/processed/labels.csv
data/processed/splits.json
db/drugs_saureus.csv
```

Optional frozen embedding caches:

```text
data/processed/esm2_embeddings.parquet
data/processed/dnabert2_embeddings.parquet
```

Each embedding Parquet must have one row per `genome_id`, a unique genome index (or a
`genome_id` column), and numeric embedding columns. Embeddings must cover all 2,542
genomes. The protein FASTA and DNA-region FASTA files are inputs used to *create* these
caches; the ensemble does not read raw sequence after the caches exist.

You may keep embedding files elsewhere and pass explicit paths:

```bash
python -m genome_firewall.model_ensemble \
  --esm2-embeddings /path/to/esm2_embeddings.parquet \
  --dnabert2-embeddings /path/to/dnabert2_embeddings.parquet
```

On Kaggle, use paths under `/kaggle/input/<dataset-name>/...`. On Colab, use paths under
`/content/drive/MyDrive/...`. The local Git clone cannot see files on your laptop when the
notebook is running on Kaggle or Colab.

## Feature setups

The script always runs `genotype_only`. It automatically adds these when the matching
embedding cache exists:

- `esm2_only`
- `genotype_plus_esm2`
- `dnabert2_only`
- `genotype_plus_dnabert2`

The optional three-source setup is deliberately off by default. Run it only after both
embeddings help independently:

```bash
python -m genome_firewall.model_ensemble --include-combined
```

Frozen embeddings do not need to be regenerated when duplicate groups or supervised
splits change. Scaling is fitted separately inside every training fold. Supervised heads,
calibrators, ensembles, and metrics must be retrained after a split or weighting change.

## Commands

Local/Conda:

```bash
conda env create -f environment.yml   # first time only
conda activate genome-firewall
make split                            # needs raw FASTAs for Mash
make ensemble
```

Quick smoke test:

```bash
python -m genome_firewall.model_ensemble --quick --antibiotics cefoxitin
```

Kaggle/Colab when only processed data and embedding caches are available:

```bash
python -m genome_firewall.model_ensemble \
  --esm2-embeddings /absolute/notebook/path/esm2_embeddings.parquet \
  --dnabert2-embeddings /absolute/notebook/path/dnabert2_embeddings.parquet
```

Do not rerun `make split` remotely unless the 2,542 raw genome FASTAs and Mash are also
available. The repository's committed `splits.json` can be used directly.

## Outputs: what to look at

Everything appears under `reports/soft_ensemble/`:

- `model_comparison.csv`: one clear table showing every antibiotic × feature setup ×
  model, with Brier, balanced accuracy, recall R/S, F1, AUROC, PR-AUC, no-call rate, and
  weighted versions of all headline metrics.
- `selected_feature_setup.csv`: the setup selected without looking at test.
- `train_oof_feature_comparison.csv`: grouped train-OOF evidence behind that selection.
- `test_predictions.csv`: calibrated per-genome probabilities and no-call flags.
- `per_cluster_metrics.csv`: performance for every held-out genetic cluster.
- `oof_model_disagreement.csv`: whether the three base models are actually diverse.
- `l1_coefficients.csv`: explainable L1 associations, marked as statistical—not causal.
- `reliability_<antibiotic>.png`: calibration plot for the train-OOF-selected setup.
- `run_config.json`: exact paths and settings used.

Fitted models are saved under `data/processed/ensemble_models/`.

The soft ensemble is not automatically declared the winner. If it does not improve
duplicate-weighted held-out Brier over the best single model, report and use the simpler
single model.

> Research prototype only. Confirm every result with standard laboratory testing; a
> trained professional makes the decision.
