# BioShield AI

**An AI Decision-Support System for Antibiotic Resistance Prediction**

Built at Hack-Nation 2026 by Jason · Ved · Cassie · Shashwat

---

## Overview

Antibiotic-resistant infections are associated with an estimated 4.7 million deaths annually, with 1.3 million directly attributable to resistant bacteria. Standard laboratory antibiotic susceptibility testing (AST) typically takes 1–3 days to return results. During that window, clinicians must select a treatment before knowing which antibiotics will work.

BioShield AI addresses this gap. Given a reconstructed bacterial genome (FASTA), it predicts, within minutes, the likelihood that each antibiotic in a curated panel will succeed or fail — well ahead of standard lab turnaround.

> **Research prototype.** BioShield AI is a decision-support tool. It does not replace laboratory confirmation or clinical judgment, and every prediction must be verified through standard AST before informing treatment.

---

## What It Does

| Capability | Description |
|---|---|
| Genome input | Accepts `.fna` / `.fasta` files from whole-genome sequencing |
| Resistance prediction | Per-antibiotic classification: likely to work / likely to fail / no-call |
| Calibrated confidence | Every prediction is accompanied by a calibrated confidence score |
| Evidence transparency | Surfaces the specific resistance genes or mutations driving each prediction |
| Target gate | Confirms the antibiotic's molecular target is present before predicting |
| Honest uncertainty | Returns a no-call rather than a forced prediction when evidence is weak or conflicting |

---

## Pipeline

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
│   FASTA     │────▶│  AMRFinderPlus   │────▶│   Feature Matrix    │────▶│  Per-Antibiotic       │
│   Genome    │     │  (NCBI Tool)     │     │ (Presence / Absence)│     │  XGBoost Model        │
└─────────────┘     └──────────────────┘     └────────────────────┘     └───────────┬───────────┘
                                                                                       │
                                                                                       ▼
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
│  Streamlit  │◀────│  Decision Report │◀────│    Target Gate      │◀────│   Calibrated           │
│  App        │     │                  │     │   (Drug Target)     │     │   Predictions          │
└─────────────┘     └──────────────────┘     └────────────────────┘     └──────────────────────┘
```

| Stage | Description | Key Output |
|---|---|---|
| Genome Reader | Converts FASTA → AMR gene presence/absence features via AMRFinderPlus | `features.parquet` |
| Predictor | Trains a per-antibiotic, calibrated XGBoost model | `data/processed/final_models/*.pkl` |
| Decision Report | Streamlit app presenting predictions, confidence, and supporting evidence | Interactive clinical demo |

---

## Model

BioShield AI's deployed model is **XGBoost** — one calibrated classifier trained per antibiotic.

**Evaluation methodology:**
- All labeled genomes are retained, but near-identical genomes (by whole-genome Mash distance) receive inverse-group weighting so that repeated lineages cannot dominate training or evaluation.
- Feature configuration is selected via grouped out-of-fold Brier score computed strictly within the training set, never against the held-out test set.
- Final deployment models are refit on every labeled genome, with sigmoid calibration learned from grouped out-of-fold predictions.

**Current best result:** ~94% accuracy on held-out grouped test data for [antibiotic name — confirm before publishing]. Per-antibiotic performance varies; consult the current XGBoost evaluation report for the full breakdown rather than relying on any single headline figure.

> An external, held-out dataset is recommended for an unbiased final evaluation of production performance.

To reproduce the evaluation:

```bash
make split       # whole-genome Mash groups; requires local raw FASTAs
make evaluate
```

To refit the deployed model on all labeled data:

```bash
make final-train
```

This tunes one XGBoost classifier per antibiotic, learns calibration from grouped out-of-fold predictions across the full labeled set, refits on every labeled row, and writes artifacts to `data/processed/final_models/`.

Further detail: [`docs/MODEL_CARD.md`](docs/MODEL_CARD.md) and [`docs/MODEL_SELECTION.md`](docs/MODEL_SELECTION.md).

---

## Quickstart

### Prerequisites

- Python 3.11+
- Conda (recommended)
- NCBI AMRFinderPlus

### Installation

```bash
git clone https://github.com/JasonL1238/Hacknation-Hackathon.git
cd Hacknation-Hackathon

# Create the conda environment (includes a runtime-pinned AMRFinderPlus install)
conda env create -f environment.yml
conda activate genome-firewall
python -m pip install -e .

# Existing environments can instead run:
make amr-setup

# Build features and refit the deployed XGBoost models on all data
make all

# Launch the Streamlit demo
streamlit run app/streamlit_app.py
```

### Makefile Commands

| Command | Description |
|---|---|
| `make amr-setup` | Install NCBI AMRFinderPlus |
| `make download` | Download genomes and AST results from BV-BRC |
| `make annotate` | Run AMRFinderPlus on all genomes |
| `make featurize` | Generate the feature matrix |
| `make split` | Create grouped train/calibration/test splits |
| `make train` | Train the baseline model used by the app |
| `make calibrate` | Calibrate the app baseline on the dedicated calibration split |
| `make evaluate` | Evaluate the app baseline on the held-out grouped test set |
| `make final-train` | Refit calibrated XGBoost on all labeled genomes for deployment |
| `make all` | Run the complete pipeline |
| `make app` | Launch the Streamlit demo |

---

## Project Structure

```
Hacknation-Hackathon/
├── CLAUDE.md              # agent rules for this repo
├── PLAN.md, README.md     # project plan / overview
├── Makefile               # make all: download → annotate → featurize → split → train → calibrate → evaluate
├── environment.yml, requirements.txt, pyproject.toml
│
├── app/                            # Streamlit frontend
│   ├── streamlit_app.py            # entrypoint
│   ├── auth.py, database.py, supabase_client.py, storage.py
│   ├── pdf_intake.py, icons.py
│   ├── pages_impl/                 # one module per screen
│   │   ├── overview.py, new_analysis.py, analysis_view.py
│   │   ├── patients.py, patient_workspace.py, cases.py
│   │   ├── reports.py, report_view.py, queue.py
│   │   ├── model_info.py, settings.py, common.py
│   └── ui/
│       ├── components.py, shell.py, theme.py
│
├── src/genome_firewall/            # core ML/bio pipeline (installable package)
│   ├── acquire.py       # genome download (BV-BRC/NCBI)
│   ├── annotate.py      # AMRFinderPlus annotation
│   ├── featurize.py     # feature extraction
│   ├── labels.py        # resistance label derivation
│   ├── split.py         # cluster-based train/cal/test split
│   ├── model_baseline.py, model_ensemble.py, model_select.py
│   ├── calibrate.py, ensemble_calibration.py
│   ├── final_train.py
│   ├── evaluate.py      # metrics, reliability, per-group breakdown
│   ├── report.py        # per-antibiotic report objects
│   └── serving.py
│
├── config/saureus.yaml             # pipeline config
├── db/
│   ├── drugs_saureus.csv           # target-gate drug/gene mapping
│   └── schema.sql
│
├── data/
│   ├── raw/                        # downloaded genomes (gitignored)
│   ├── interim/                    # AMRFinder output, measured labels (gitignored)
│   └── processed/                  # features.parquet, labels.csv, splits.json,
│                                    #   metrics.json, split_audit.json, models/
│
├── models/                         # per-model writeups (00_OVERVIEW.md … 23_soft_voting_ensemble.md)
├── experiments/model_bakeoff/
├── reports/                        # reliability.png, pr_curves.png, model_selection/, soft_ensemble/
│
├── docs/
│   ├── DATA_SPEC.md                # shared schema contract (don't change without a sync)
│   ├── DECISIONS.md                # adversarial-review log (required per CLAUDE.md)
│   ├── MODEL_CARD.md, MODEL_SELECTION.md, RESPONSIBLE_AI.md, RISKS.md
│   └── DEPLOY_STREAMLIT.md
│
├── scripts/
│   ├── setup_amrfinder.sh          # `make amr-setup`
│   └── resplit_mash.py
│
└── tests/
    ├── test_model_ensemble.py
    └── test_supabase_client.py
```

---

## Data Sources

| Source | Description |
|---|---|
| [BV-BRC](https://bv-brc.org) (formerly PATRIC) | 15,000+ bacterial genomes with lab-measured AST results |
| [AMRFinderPlus](https://github.com/ncbi/amr) | NCBI tool for resistance gene and mutation detection |
| [ResFinder](https://genepi.food.dtu.dk/resfinder) | Acquired resistance gene and mutation identification |
| [CARD](https://card.mcmaster.ca) | Comprehensive Antibiotic Resistance Database |

---

## Responsible AI

| Principle | Implementation |
|---|---|
| Defensive by design | Never designs, modifies, or suggests changes to organisms |
| Honest generalization | Grouped splits by genetic cluster; unseen clusters held out for test |
| Calibrated confidence | Reliability plots and Brier scores reported; no overconfident predictions |
| Explicit no-call | Returns no-call when evidence is weak or conflicting |
| Transparent evidence | Separates known resistance genes from statistical associations |
| Human oversight | Mandatory lab confirmation; the system never makes treatment decisions |

Full detail in [`docs/RESPONSIBLE_AI.md`](docs/RESPONSIBLE_AI.md) and [`docs/RISKS.md`](docs/RISKS.md).

---

## Deployment

The application is prepared for Streamlit Community Cloud with a pinned Conda environment, a Bioconda AMRFinderPlus runtime, final XGBoost model artifacts, and per-visitor Supabase authentication clients. An optional, explicitly enabled synthetic guest workspace is available for public demonstrations. Exact configuration values and secrets setup are documented in [`docs/DEPLOY_STREAMLIT.md`](docs/DEPLOY_STREAMLIT.md).

When the AMRFinderPlus database is absent, the app provisions it at runtime and then verifies that its version matches the frozen contract in `data/processed/feature_spec.json`. Inference fails safely if the versions differ.

The upload path is synchronous and single-genome. FASTA bytes are held only until AMRFinderPlus and model inference complete; the temporary FASTA and TSV are deleted on success or failure. Results and submission metadata persist in the authenticated Streamlit session, but the genome itself is never uploaded to Supabase Storage.

Free-tier hosting is suitable only for this research demonstration. It is not an appropriate environment for clinical workloads, protected health information, uptime guarantees, or regulated deployment.

---

## Team

Jason · Ved · Cassie · Shashwat

## License

MIT License — see [LICENSE](LICENSE) for details.

## References

- AMRFinderPlus — [github.com/ncbi/amr](https://github.com/ncbi/amr)
- BV-BRC — [bv-brc.org](https://bv-brc.org)
- ResFinder — [genepi.food.dtu.dk/resfinder](https://genepi.food.dtu.dk/resfinder)
- CARD — [card.mcmaster.ca](https://card.mcmaster.ca)

---

## Disclaimer

This is a research prototype for demonstration purposes only. Predictions are based on historical bacterial genome data and do not establish that the system is safe, accurate, or suitable for real healthcare decisions. Every prediction must be confirmed by standard laboratory testing. A trained healthcare or laboratory professional must make all treatment decisions.
