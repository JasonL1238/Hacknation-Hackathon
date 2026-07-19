# Local Model Bakeoff

This folder is the single workspace for comparing the focused model research set. It
does not create new random splits. Every experiment must use the committed Mash split
and duplicate-family weights.

## Start here

From the repository root:

```bash
conda activate genome-firewall
python experiments/model_bakeoff/check_setup.py
```

The checker validates the feature/label/split contract, confirms that neither Mash
clusters nor strict duplicate families cross splits, prints effective per-antibiotic
training sizes, and reports local package availability.

## What can run locally

| Model | Local status | Entry point |
|---|---|---|
| L2 logistic | ready | `make train && make calibrate && make evaluate` |
| L1 logistic | ready | existing ensemble trainer |
| HistGradientBoosting | ready | existing ensemble trainer |
| XGBoost | ready | existing ensemble trainer |
| Soft ensemble | ready, historical comparison only | existing ensemble trainer |
| Elastic Net | CPU-feasible, implementation pending | model plan 02 |
| Explainable Boosting Machine | CPU-feasible, `interpret` missing | model plan 14 |
| TabPFN | conditional | model plan 13 |

The existing genotype-only comparison can be reproduced with:

```bash
PYTHONPATH=src python -m genome_firewall.model_ensemble \
  --setups genotype_only \
  --voting inverse-brier
```

That command evaluates the held-out test set. The test has already been inspected, so do
not use another run to choose new models or hyperparameters.

## Protocol for new candidates

Elastic Net, EBM, and TabPFN must first be compared using duplicate-weighted grouped OOF
predictions inside `train` only:

1. Group folds by `cluster_id`.
2. Use normalized row weight `1 / labeled dedup-group size` in every fit.
3. Select hyperparameters by weighted OOF Brier, with weighted balanced accuracy only as
   a tie-break.
4. Keep `cal` for the final probability calibrator.
5. Do not inspect `test` again for model selection. A new external holdout is required for
   a fresh unbiased final claim.

TabPFN is the exception to “all local.” The official package recommends a GPU and says
CPU inference is practical only for small datasets around 1,000 rows or fewer. It also
downloads a gated checkpoint on first use. More importantly, the standard classifier
must expose fit-time `sample_weight`; if it does not, skip it rather than violating the
duplicate policy.

## Files

- `registry.json`: retained models, status, dependency, and intended runner.
- `check_setup.py`: read-only local validation.
- `results/`: generated experiment outputs; ignored by Git.

> Research prototype—confirm every result with standard laboratory testing; a trained
> professional makes the decision.
