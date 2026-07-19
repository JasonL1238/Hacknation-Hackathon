# 🧬 BioShield AI

### An AI Defense System Against Superbugs

## 🎯 The Problem

Antibiotic-resistant infections are associated with **4.7 million deaths** annually, with **1.3 million** directly attributable to resistant bacteria. Doctors currently wait **1–3 days** for laboratory results before knowing which antibiotic will work — and during that window, they must guess, often incorrectly.

**BioShield AI changes this.**

---

## 🚀 What It Does

**BioShield AI** takes a reconstructed bacterial genome (FASTA) and predicts, within minutes, which antibiotics are likely to work or fail — well before standard lab results arrive.

| Feature | Description |
|---|---|
| **Genome Input** | Accepts `.fna` / `.fasta` files from sequencing |
| **Resistance Prediction** | Per-antibiotic predictions: **likely to work / likely to fail / no-call** |
| **Confidence Calibration** | Every prediction includes a calibrated confidence score |
| **Evidence Transparency** | Shows which genes or mutations drove the prediction |
| **Target Gate** | Verifies the drug's molecular target is present |
| **Honest Uncertainty** | Returns **no-call** when evidence is weak or conflicting |

> ⚠️ **Research Prototype** — Every result must be confirmed by standard laboratory testing. This tool is decision support only and does not replace clinical judgment.

---

## 📊 How It Works

### Pipeline Overview

```
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
│   FASTA     │────▶│  AMRFinderPlus   │────▶│   Feature Matrix    │────▶│  Per-Antibiotic       │
│   Genome    │     │  (NCBI Tool)     │     │ (Presence/Absence)  │     │  Calibrated Model     │
└─────────────┘     └──────────────────┘     └────────────────────┘     └───────────┬───────────┘
                                                                                       │
                                                                                       ▼
┌─────────────┐     ┌──────────────────┐     ┌────────────────────┐     ┌──────────────────────┐
│  Streamlit  │◀────│  Decision Report │◀────│    Target Gate      │◀────│   Antibiotic          │
│  Demo App   │     │                  │     │   (Drug Target)     │     │   Predictions          │
└─────────────┘     └──────────────────┘     └────────────────────┘     └──────────────────────┘
```

### Three Core Modules

| Module | Description | Key Deliverable |
|---|---|---|
| **01 — Genome Reader** | Converts FASTA → AMR gene presence/absence features | `features.parquet` |
| **02 — Predictor** | Trains per-antibiotic models with calibration | `.pkl` models + predictions |
| **03 — Decision Report** | Streamlit app with confidence, evidence, no-call | Interactive demo |

---

## 🏆 Model Performance

### Top Performing Models

| Rank | Model | Overall Accuracy | Balanced Accuracy |
|:---:|---|---|---|
| 🥇 | **XGBoost** | **93.50%** | 90.70% |
| 🥈 | HistGradientBoosting | 91.62% | 91.01% |
| 🥉 | L1/Elastic-Net (Lasso) | 91.46% | 91.26% |

### Recommended Production Model: Soft-Voting Ensemble

The top 3 models (XGBoost, HistGradientBoosting, L1/Elastic-Net) are combined via **soft-voting** into a robust, well-calibrated ensemble.

**Why these three?**
- **XGBoost** — Highest raw accuracy (93.50%)
- **HistGradientBoosting** — Best balanced accuracy (91.01%)
- **L1/Elastic-Net** — Strong regularization, interpretable feature selection (91.46%) raw accuracy

| Model | Weight in Ensemble |
|---|---|
| XGBoost | 1.5 |
| HistGradientBoosting | 1.0 |
| L1/Elastic-Net | 0.8 |

**Expected Performance:** ~94% accuracy with better calibration and generalization than any single model.

### Per-Antibiotic Performance (Soft-Voting Ensemble)

| Antibiotic | Accuracy | Balanced Acc | F1 Score | Brier Score |
|---|---|---|---|---|
| Gentamicin | 95.68% | 93.37% | 0.8800 | 0.0490 |
| Cefoxitin | 95.77% | 95.73% | 0.9708 | 0.0438 |
| Erythromycin | 91.61% | 92.30% | 0.9297 | 0.0793 |
| Tetracycline | 89.57% | 87.63% | 0.8079 | 0.0676 |
| Clindamycin | 84.62% | 84.44% | 0.8700 | 0.1175 |
| Ciprofloxacin | 92.60% | 92.83% | 0.9288 | 0.0611 |

---

## 🛠️ Quickstart

### Prerequisites

- Python 3.10+
- Conda (recommended)
- NCBI AMRFinderPlus

### Installation

```bash
# Clone the repository
git clone https://github.com/JasonL1238/Hacknation-Hackathon.git
cd Hacknation-Hackathon

# Create conda environment
conda env create -f environment.yml
conda activate genome-firewall

# Install AMRFinderPlus
make amr-setup

# Run the full pipeline
make all

# Launch the Streamlit demo
streamlit run app/streamlit_app.py
```

### Makefile Commands

| Command | Description |
|---|---|
| `make amr-setup` | Install NCBI AMRFinderPlus |
| `make download` | Download genomes + AST from BV-BRC |
| `make annotate` | Run AMRFinderPlus on all genomes |
| `make featurize` | Generate feature matrix |
| `make split` | Create grouped train/cal/test splits |
| `make train` | Train per-antibiotic models |
| `make calibrate` | Calibrate confidence scores |
| `make eval` | Evaluate models on held-out test set |
| `make all` | Run the complete pipeline |
| `make app` | Launch Streamlit demo |

---

## 📁 Project Structure

```
Hacknation-Hackathon/
├── app/
│   └── streamlit_app.py          # Module 03: Decision Report demo
├── config/
│   └── saureus.yaml              # Configuration for S. aureus
├── data/
│   ├── raw/                      # Genomes + AST (gitignored)
│   ├── interim/amrfinder/        # AMRFinderPlus outputs
│   └── processed/                # Feature matrix, labels, splits
├── db/
│   └── drugs_saureus.csv         # Curated drug database
├── docs/
│   ├── DATA_SPEC.md              # Data contract
│   ├── MODEL_CARD.md             # Model documentation
│   ├── DECISIONS.md              # Design decisions
│   └── RESPONSIBLE_AI.md         # Responsible AI practices
├── models/                       # Trained model files
├── reports/                      # Metrics and evaluation
├── src/genome_firewall/
│   ├── acquire.py                # BV-BRC data download
│   ├── annotate.py               # AMRFinderPlus runner
│   ├── featurize.py              # Feature extraction
│   ├── split.py                  # Grouped split (de-dup)
│   ├── labels.py                 # SIR/MIC → binary R/S
│   ├── model_baseline.py         # Per-antibiotic training
│   ├── calibrate.py              # Confidence calibration
│   ├── nocall.py                 # No-call / OOD detection
│   ├── target_gate.py            # Drug target gate
│   ├── evaluate.py               # Metrics & evaluation
│   └── report.py                 # Structured report generation
├── environment.yml               # Conda environment
├── Makefile                      # Pipeline automation
├── PLAN.md                       # Full technical plan
└── README.md                     # This file
```

---

## 🔬 Data Sources

| Source | Description |
|---|---|
| [BV-BRC](https://bv-brc.org) (ex-PATRIC) | 15,000+ bacterial genomes with lab-measured AST results |
| [AMRFinderPlus](https://github.com/ncbi/amr) | NCBI tool for resistance gene and mutation detection |
| [ResFinder](https://genepi.food.dtu.dk/resfinder) | Acquired resistance gene and mutation identification |
| [CARD](https://card.mcmaster.ca) | Comprehensive Antibiotic Resistance Database |

---

## 🛡️ Responsible AI

BioShield AI is built with strict responsible AI principles:

| Principle | Implementation |
|---|---|
| **Defensive by Design** | Never designs, modifies, or suggests changes to organisms |
| **Honest Generalization** | Grouped splits by genetic cluster; unseen clusters held out for test |
| **Calibrated Confidence** | Reliability plots and Brier scores; no overconfident predictions |
| **Explicit No-Call** | Returns no-call when evidence is weak or conflicting |
| **Transparent Evidence** | Separates known resistance genes from statistical associations |
| **Human Oversight** | Mandatory lab confirmation; the system never makes treatment decisions |

---

## 👥 Team

Jason · Ved · Cassie · Shashwat

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.

---

## 📚 References

- AMRFinderPlus: [github.com/ncbi/amr](https://github.com/ncbi/amr)
- BV-BRC: [bv-brc.org](https://bv-brc.org)
- ResFinder: [genepi.food.dtu.dk/resfinder](https://genepi.food.dtu.dk/resfinder)
- CARD: [card.mcmaster.ca](https://card.mcmaster.ca)

---

## ⚠️ Disclaimer

This is a research prototype for demonstration purposes. Predictions are based on historical bacterial genome data and do not prove that the system is safe, accurate, or suitable for real healthcare decisions. Every prediction must be confirmed by standard laboratory testing. A trained healthcare or laboratory professional must make all treatment decisions.

---

<p align="center">Built at Hack-Nation 2026</p>
