# Genome Firewall 🧬🛡️

An AI defense system against superbugs — Hack-Nation Challenge 06.

Genome Firewall takes a reconstructed **Staphylococcus aureus** genome (FASTA) and
predicts, for each of several antibiotics, whether it is **likely to fail**, **likely to
work**, or **no-call** — with a calibrated confidence score, an evidence category, and the
supporting genes/mutations. It is **strictly defensive** decision support: it predicts and
explains resistance that already exists and must never design or modify organisms.

> ⚠️ **Research prototype.** Every result must be confirmed by standard laboratory
> testing. This is decision support only — a trained healthcare or laboratory
> professional makes the treatment decision.

## Start here
- **[PLAN.md](PLAN.md)** — the full technical plan.
- **[CLAUDE.md](CLAUDE.md)** — rules every contributor (and their AI agent) must follow.
- **[docs/DATA_SPEC.md](docs/DATA_SPEC.md)** — the frozen data/interface contracts.
- **Pick up a task:** PLAN.md → "Build order" lists the pipeline stages in dependency
  order — take whichever is next and hasn't been started.

## The pipeline
```
FASTA → AMRFinderPlus → feature matrix → per-antibiotic calibrated model + target gate → report
```
Three required modules: **01 Genome Reader**, **02 Predictor**, **03 Decision Report**
(Streamlit), plus an ESM-2 deep-learning stretch compared honestly against the baseline.

## Quickstart
```bash
conda env create -f environment.yml
conda activate genome-firewall
make amr-setup                        # install NCBI AMRFinderPlus (github.com/ncbi/amr)
make all                               # full pipeline, real data only
streamlit run app/streamlit_app.py    # the demo
```

## How the team works
No fixed per-person ownership — anyone can pick up any part of the pipeline. The stages
have a real sequential dependency (data → features → model → demo), so work roughly in
that order. No synthetic or placeholder data anywhere in the repo — every file is real.
See [PLAN.md](PLAN.md) → "Build order".
