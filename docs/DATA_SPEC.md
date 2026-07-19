# DATA_SPEC.md — Frozen interface contracts (the seams between pipeline stages)

> **This file is a shared seam. Do not change a schema without a 2-minute team sync** —
> changing a contract breaks whoever consumes it. Every stage's real output must
> validate against these schemas. No synthetic or placeholder data — every file these
> schemas describe must come from a real source (BV-BRC/NCBI) or an actual pipeline run.

All paths are relative to the repo root. `genome_id` is the join key everywhere (string,
e.g. a BV-BRC genome id like `1280.1234`).

---

## 1. `data/processed/features.parquet`  (produced by the feature pipeline → consumed by modeling)
- One row per genome. **Index:** `genome_id` (str).
- **Columns:** binary `int8` presence/absence — AMR gene symbols (e.g. `mecA`, `blaZ`,
  `ermC`, `tetK`) and specific point mutations (e.g. `gyrA_S84L`, `grlA_S80F`).
- Column set is the **union across the dataset**, frozen in `feature_spec.json`.
- No missing values (absent = 0).

## 2. `data/processed/feature_spec.json`  (feature pipeline → modeling & demo)
```json
{
  "version": "sha256-of-sorted-columns",
  "columns": ["blaZ", "mecA", "ermC", "tetK", "gyrA_S84L", "..."],
  "amrfinder_db_version": "2024-xx-xx.x",
  "organism_flag": "Staphylococcus_aureus"
}
```
Inference (the demo) MUST build feature vectors in exactly this column order.

## 3. `data/processed/labels.csv`  (produced by data acquisition → consumed by modeling)
| column | type | notes |
|---|---|---|
| `genome_id` | str | join key |
| `antibiotic` | str | standardized name, matches `db/drugs_saureus.csv` |
| `label` | str | `R` (resistant / likely-to-fail) or `S` (susceptible / likely-to-work) |
| `source` | str | e.g. `BV-BRC` |
| `method` | str | lab typing method (MIC / disk); must be **lab-measured**, not predicted |

One row per (genome_id, antibiotic). Intermediate "I" resolved per `labels.py` rule
(default: merged into R; documented in DECISIONS.md).

## 4. `data/processed/splits.json`  (produced by the split/modeling stage)
```json
{ "1280.1234": {"split": "train", "cluster_id": 7,
                  "dedup_group_id": 12, "dedup_group_size": 3},
  "1280.5678": {"split": "test",  "cluster_id": 41,
                  "dedup_group_id": 99, "dedup_group_size": 1} }
```
`split` ∈ {`train`, `cal`, `test`}. **Invariant:** every genome in a given `cluster_id`
has the same `split` (no cluster spans splits — enforced by an assert in `split.py`).
`dedup_group_id` identifies near-identical genomes from the stricter Mash threshold.
Rows are retained; supervised training uses inverse labeled-group-size weights so repeated
genomes do not dominate. `split_audit.json` records the distance method and group counts.

## 5. `db/drugs_saureus.csv`  (produced by data acquisition → consumed by modeling)
| column | type | notes |
|---|---|---|
| `antibiotic` | str | standardized name (join key to labels) |
| `drug_class` | str | e.g. beta-lactam, fluoroquinolone, macrolide |
| `target_genes` | str | `;`-separated gene symbols that are the drug's molecular target |
| `known_markers` | str | `;`-separated known resistance genes/mutations for this drug |
| `standardized_name` | str | canonical display name |

## 6. Report object  (produced by `report.py` → consumed by the Streamlit app)
One dict per antibiotic (the app renders a list of these):
```python
{
  "antibiotic": "oxacillin",
  "verdict": "fail",              # "fail" | "work" | "nocall"
  "confidence": 0.94,             # calibrated probability of the verdict, 0..1
  "evidence_category": "i",       # "i" known gene/mutation | "ii" statistical-only | "iii" no signal
  "supporting_features": ["mecA"],# named genes/mutations behind the call
  "target_present": True,         # from the deterministic target gate
  "reasons": ["mecA detected (known oxacillin resistance determinant)"]
}
```

## 7. `data/processed/metrics.json`  (produced by evaluation → consumed by the demo)
Per-antibiotic and per-genetic-group: `balanced_accuracy`, `recall_R`, `recall_S`, `f1`,
`auroc`, `pr_auc`, `brier`, `nocall_rate`, `accuracy_on_called`. Plus reliability &
PR-curve PNGs in `reports/`.

## 8. Soft-ensemble training outputs

`python -m genome_firewall.model_ensemble` writes to `reports/soft_ensemble/`:

- `model_comparison.csv`: weighted and ordinary test metrics for every antibiotic,
  feature setup, base learner, and the soft ensemble.
- `train_oof_feature_comparison.csv` and `selected_feature_setup.csv`: feature selection
  evidence computed only from grouped out-of-fold predictions inside train.
- `test_predictions.csv`, `per_cluster_metrics.csv`, `oof_model_disagreement.csv`,
  `l1_coefficients.csv`, reliability plots, and `run_config.json`.

Fitted artifacts are written to `data/processed/ensemble_models/` and are intentionally
gitignored.
