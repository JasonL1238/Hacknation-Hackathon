# Person C — Modeling, Split, Calibration, Evaluation, DL stretch (Module 02) — the rigor core

> Read [CLAUDE.md](../../CLAUDE.md) and [docs/DATA_SPEC.md](../DATA_SPEC.md) first. Work on
> branch `feat/model`. **Never blocked** — train on the **synthetic** `features.parquet` +
> `labels.csv` from `_synth.py` until A/B deliver, then swap to real (same paths). This
> workstream is where the hackathon is won: ML rigor & calibration is the judged priority.

## You own (edit freely)
`src/genome_firewall/`: `split.py`, `model_baseline.py`, `calibrate.py`, `nocall.py`,
`target_gate.py`, `evaluate.py`, `embed_esm.py`, `report.py`.

## Deliverables (the contracts you produce)
1. **`data/processed/splits.json`** — DATA_SPEC §4 (grouped, no cluster spans splits).
2. Trained + calibrated per-antibiotic models (pickled under `data/processed/models/`).
3. **Report objects** via `report.py` — DATA_SPEC §6.
4. **`data/processed/metrics.json`** + reliability/PR PNGs in `reports/` — DATA_SPEC §7.

## Tasks (in dependency order, but all doable on synthetic first)
1. **De-dup + grouped split** (`split.py`): Mash (or skani ANI) sketches → de-dup
   near-identical genomes (~Mash <0.0002 / ANI ≥99.98%), report count collapsed →
   single-linkage cluster at a coarser threshold (tune ~0.001–0.005; cross-check MLST
   clonal complexes) → assign **whole clusters** to train/cal/test. **Assert no cluster
   spans splits.** Hold out some clusters entirely unseen in training. Justify threshold
   in `docs/DECISIONS.md`.
2. **Baseline** (`model_baseline.py`): one L2-regularized `LogisticRegression`
   (`class_weight="balanced"`) per antibiotic on the presence/absence matrix.
3. **Calibration** (`calibrate.py`): isotonic (or Platt) fit **on the `cal` split only**;
   reliability diagram + Brier on the **`test` split**.
4. **Target gate** (`target_gate.py`): read `db/drugs_saureus.csv`; never allow "work"
   from marker-absence alone — require target present; else resistance/no-call.
5. **No-call** (`nocall.py`): trigger on (a) calibrated p in ~[0.4,0.6], (b) OOD (distance
   to nearest training cluster, or unseen AMR genes/mutations), (c) target gate. Report
   no-call rate + accuracy-on-called.
6. **Evidence category** (`report.py`): (i) known catalog gene/mutation drove the call,
   (ii) statistical-only (coefficient/SHAP — label as *not proven causal*), (iii) no
   signal. Build the report object per DATA_SPEC §6.
7. **Metrics** (`evaluate.py`): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC
   per drug, Brier, no-call rate, accuracy-on-called, **per-genetic-group** breakdown incl.
   unseen groups. Write `metrics.json` + PNGs.
8. **DL stretch** (`embed_esm.py`): ESM-2 (`facebook/esm2_t12_35M`/`t30_150M`) on
   AMRFinder-flagged proteins, mean-pool per genome (MPS), concat/replace features,
   retrain on the **same splits + same calibration**, report deltas honestly. Not beating
   the baseline is a valid, honest result.

## Definition of done
Splits provably leak-free; calibration curve tracks the diagonal on held-out; `report.py`
emits DATA_SPEC-valid objects; `metrics.json` has per-group breakdown; DL-vs-baseline
deltas computed on identical splits.

## Self-questioning before you call it done
Could any near-identical genome span train/test? Is calibration fit only on `cal`? Is any
"work" verdict resting on marker-absence without target-present? Is any SHAP/coefficient
presented as biological cause? Do we no-call enough, or forcing yes/no?
