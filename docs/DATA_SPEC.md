# DATA_SPEC.md — Frozen interface contracts (the seams between the 4 workstreams)

> **This file is a shared seam. Do not change a schema without a 2-minute team sync** —
> changing a contract breaks whoever consumes it. Everyone builds against these schemas
> and against the synthetic data emitted by `src/genome_firewall/_synth.py`, then real
> files overwrite the synthetic ones at the same paths during integration.

All paths are relative to the repo root. `genome_id` is the join key everywhere (string,
e.g. a BV-BRC genome id like `1280.1234`).

---

## 1. `data/processed/features.parquet`  (produced by Person B → consumed by Person C)
- One row per genome. **Index:** `genome_id` (str).
- **Columns:** binary `int8` presence/absence — AMR gene symbols (e.g. `mecA`, `blaZ`,
  `ermC`, `tetK`) and specific point mutations (e.g. `gyrA_S84L`, `grlA_S80F`).
- Column set is the **union across the dataset**, frozen in `feature_spec.json`.
- No missing values (absent = 0).

## 2. `data/processed/feature_spec.json`  (Person B → Person C & D)
```json
{
  "version": "sha256-of-sorted-columns",
  "columns": ["blaZ", "mecA", "ermC", "tetK", "gyrA_S84L", "..."],
  "amrfinder_db_version": "2024-xx-xx.x",
  "organism_flag": "Staphylococcus_aureus"
}
```
Inference (the demo) MUST build feature vectors in exactly this column order.

## 3. `data/processed/labels.csv`  (produced by Person A → consumed by Person C)
| column | type | notes |
|---|---|---|
| `genome_id` | str | join key |
| `antibiotic` | str | standardized name, matches `db/drugs_saureus.csv` |
| `label` | str | `R` (resistant / likely-to-fail) or `S` (susceptible / likely-to-work) |
| `source` | str | e.g. `BV-BRC` |
| `method` | str | lab typing method (MIC / disk); must be **lab-measured**, not predicted |

One row per (genome_id, antibiotic). Intermediate "I" resolved per `labels.py` rule
(default: merged into R; documented in DECISIONS.md).

## 4. `data/processed/splits.json`  (produced by Person C)
```json
{ "1280.1234": {"split": "train", "cluster_id": 7},
  "1280.5678": {"split": "test",  "cluster_id": 41} }
```
`split` ∈ {`train`, `cal`, `test`}. **Invariant:** every genome in a given `cluster_id`
has the same `split` (no cluster spans splits — enforced by an assert in `split.py`).

## 5. `db/drugs_saureus.csv`  (produced by Person A → consumed by Person C)
| column | type | notes |
|---|---|---|
| `antibiotic` | str | standardized name (join key to labels) |
| `drug_class` | str | e.g. beta-lactam, fluoroquinolone, macrolide |
| `target_genes` | str | `;`-separated gene symbols that are the drug's molecular target |
| `known_markers` | str | `;`-separated known resistance genes/mutations for this drug |
| `standardized_name` | str | canonical display name |

## 6. Report object  (produced by Person C `report.py` → consumed by Person D app)
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

## 7. `data/processed/metrics.json`  (produced by Person C → consumed by Person D)
Per-antibiotic and per-genetic-group: `balanced_accuracy`, `recall_R`, `recall_S`, `f1`,
`auroc`, `pr_auc`, `brier`, `nocall_rate`, `accuracy_on_called`. Plus reliability &
PR-curve PNGs in `reports/`.

---

## Synthetic data generator — `src/genome_firewall/_synth.py`  (shared seam)
Running `python -m genome_firewall._synth` writes schema-valid **fake** versions of
files 1–4, a placeholder `db/drugs_saureus.csv`, and a sample report object at
`data/processed/sample_report.json` (file 6), so Persons C and D can build from minute
one. It only writes a file if it doesn't already exist (use `--force` to regenerate) —
this way, real outputs from A/B/C can land at the same paths and are never clobbered by
a re-run. Keep the synthetic schemas byte-compatible with this spec.
