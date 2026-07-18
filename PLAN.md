# Genome Firewall — S. aureus AMR Prediction (Hackathon Plan)

## Context

We are building **Genome Firewall** for Hack-Nation Challenge 06: a defensive research
prototype that takes a reconstructed, quality-checked **Staphylococcus aureus** genome
(FASTA) and predicts, for each of a few antibiotics, whether it is **likely to fail /
likely to work / no-call**, with a **calibrated confidence score**, an **evidence
category**, and the **supporting genes/mutations**.

Decisions locked with the user:
- **Species:** *Staphylococcus aureus* only (incl. MRSA). Great fit — resistance is
  mostly acquired-gene-driven (mecA/mecC, blaZ, ermA/B/C, tetK/M, aac(6')-aph(2''))
  plus catalogued point mutations (gyrA/grlA→fluoroquinolones), all detectable by
  AMRFinderPlus's `--organism Staphylococcus_aureus` mode.
- **Data:** we source it ourselves from **BV-BRC** (genomes + lab-measured AST). We do
  NOT have the organizer dataset; if one appears later it drops into the same pipeline.
- **Time/team:** 24–48h, team of 4.
- **Win priority:** ML rigor & calibration is the primary judged axis. The Streamlit
  demo and responsible-AI framing are mandatory deliverables we execute well but do not
  over-invest in. Multimodal/OpenAI is optional polish, gated behind a flag.
- **Model scope:** regularized logistic-regression **baseline** (the rubric's
  recommended core) **+ a DL stretch**: ESM-2 protein embeddings over AMRFinderPlus-
  flagged proteins, pooled per genome, compared honestly against the baseline on the
  same splits.

Environment already verified on the build machine: conda 25.7, Docker 27.4, Python 3.13,
scikit-learn 1.7, pandas 2.3, Streamlit 1.56, PyTorch 2.8 with **MPS (Apple GPU)**.
AMRFinderPlus is not installed but is one `conda`/`docker` command away.

---

## The self-questioning workflow (how we drive toward the best product)

We bake an **adversarial review loop** into every module. Before any module is "done",
it must survive these questions, written into `docs/DECISIONS.md` with an answer +
evidence:

1. **Leakage check** — "Could a near-identical genome be in both train and test?"
   (must be provably no, via the grouped split + de-dup report).
2. **Calibration check** — "Do the confidence scores match reality?" (reliability plot +
   Brier on the held-out set, not the train set).
3. **Honesty check** — "Is any 'likely to work' based only on absence of markers?"
   (target-gate must be enforced; evidence category must be truthful).
4. **Causation check** — "Are we presenting a SHAP/coefficient as biological proof?"
   (evidence category (ii) statistical-only must be labeled as such).
5. **Generalization check** — "Does performance hold on genetic groups unseen in
   training?" (report per-group metrics, expect a drop, report it honestly).
6. **Uncertainty check** — "Are we forcing a yes/no when we should no-call?" (report
   no-call rate + accuracy-on-called; a good no-call rate is a strength).
7. **Scope check** — "Does anything drift toward designing/modifying an organism?"
   (must be strictly predict-explain-existing-resistance).

Cadence: at the end of each integration wave, one team member plays "red team" and runs
this checklist against the current state; findings become the next tasks. Keep a running
`docs/RISKS.md`.

---

## Architecture (three required modules + stretch)

```
FASTA (S. aureus genome)
   │  Module 01 — Genome Reader
   ▼
AMRFinderPlus (--organism Staphylococcus_aureus)  →  gene/mutation presence-absence matrix
   │  (+ DL stretch: ESM-2 embeddings on flagged proteins)
   ▼  Module 02 — Predictor
Per-antibiotic calibrated classifier  +  deterministic molecular-target gate
   │
   ▼  Module 03 — Decision Report
Streamlit app: fail / work / no-call, confidence, evidence category, supporting genes,
held-out performance panel, mandatory "confirm with standard lab testing" banner
```

### Project structure
```
genome-firewall/
├── environment.yml            # conda env: python, sklearn, torch, streamlit, biopython, requests, fair-esm
├── Makefile                   # download → annotate → featurize → split → train → calibrate → eval → app
├── config/
│   └── saureus.yaml           # species, antibiotics, thresholds, paths, drug→target table pointer
├── data/
│   ├── raw/                   # genomes + AST pulled from BV-BRC (gitignored, manifest tracked)
│   ├── interim/amrfinder/     # per-genome AMRFinderPlus TSVs
│   └── processed/             # feature matrix, labels, splits, checksums
├── src/genome_firewall/
│   ├── acquire.py             # BV-BRC genome + AST download & join (module 01 data)
│   ├── annotate.py            # batch AMRFinderPlus runner (module 01)
│   ├── featurize.py           # parse AMRFinder TSV → presence-absence matrix + spec (module 01)
│   ├── split.py               # de-dup + grouped split (Mash/skani clustering)
│   ├── labels.py              # SIR/MIC → binary R/S rule
│   ├── model_baseline.py      # per-antibiotic logistic regression
│   ├── calibrate.py           # isotonic/Platt calibration + reliability/Brier
│   ├── nocall.py              # no-call logic + OOD detection
│   ├── target_gate.py         # deterministic drug→target-present gate
│   ├── embed_esm.py           # DL stretch: ESM-2 protein embeddings (MPS)
│   ├── evaluate.py            # all metrics, per-group generalization, baseline-vs-DL
│   └── report.py              # structured per-antibiotic report object + evidence category
├── app/streamlit_app.py       # Module 03 demo
├── db/drugs_saureus.csv       # curated drug DB: name, class, target gene(s), markers
└── docs/
    ├── DATA_SPEC.md  MODEL_CARD.md  DECISIONS.md  RISKS.md  RESPONSIBLE_AI.md
    └── subplans/  PERSON_A_data.md  PERSON_B_features.md  PERSON_C_model.md  PERSON_D_demo.md
```

---

## Shared foundation — do this TOGETHER FIRST (~45–60 min, one driver, others read)

This is the single most important step for 4-way parallel vibecoding. Until these
**contracts** exist and are committed to `main`, nobody else should start, because a
contract change later breaks everyone. Freeze them, then fork. Contracts live in
`docs/DATA_SPEC.md`.

**1. Repo skeleton + env.** The tree above, `environment.yml`, `config/saureus.yaml`,
`Makefile` targets (stubs OK), `.gitignore` (ignore `data/raw`, `data/interim`, model
artifacts; keep manifests). *(Scaffolded in this repo already.)*

**2. Freeze the data contracts** (in `docs/DATA_SPEC.md` — the seams between the 4
workstreams; changing one requires a 2-min team sync):
- `data/processed/features.parquet`: index `genome_id` (str) + binary int columns; plus
  `data/processed/feature_spec.json` = ordered column list + version hash.
- `data/processed/labels.csv`: `genome_id, antibiotic, label` (label ∈ {R,S}),
  `source, method`.
- `data/processed/splits.json`: `genome_id → {split: train|cal|test, cluster_id: int}`.
- `db/drugs_saureus.csv`: `antibiotic, drug_class, target_genes, known_markers,
  standardized_name`.
- **Report object** (Module 03 seam), one dict per antibiotic:
  `{antibiotic, verdict: fail|work|nocall, confidence: float, evidence_category: i|ii|iii,
  supporting_features: [str], target_present: bool, reasons: [str]}`.
- Eval artifacts: `data/processed/metrics.json` + `reports/*.png` (reliability, PR curves).

**3. Ship a synthetic data generator** (`src/genome_firewall/_synth.py`): emits
schema-valid fake `features.parquet`, `labels.csv`, `splits.json`, and a sample report
object. **This is what unblocks everyone** — the ML owner trains on synthetic features,
the demo owner renders synthetic reports, all from minute one, before any real data or
AMRFinderPlus output exists. Real files overwrite synthetic ones at integration.

**Git workflow.** After the foundation lands on `main`, each person works on their own
branch (`feat/data`, `feat/features`, `feat/model`, `feat/demo`) and merges to `main`
frequently. Because ownership is **disjoint by file/directory**, merges are near-trivial.
**Rule:** nobody edits `config/`, `docs/DATA_SPEC.md`, `_synth.py`, or another person's
files without a quick sync — those are the shared seams.

---

## Module 01 — Genome Reader (FASTA → features)

**Data acquisition (BV-BRC).** Pull *S. aureus* genomes and their **lab-measured** AST
from BV-BRC (ex-PATRIC) via its public Data API (`https://www.bv-brc.org/api/`) using
`requests` (RQL queries against the `genome`, `genome_amr`, and `genome_sequence`
resources), or the `p3-*` / BV-BRC CLI as a fallback. Key steps:
- Query `genome_amr` for `genome_name` matching *Staphylococcus aureus*, keep rows where
  `laboratory_typing_method` indicates a **measured** test (MIC/disk) and a real
  `resistant_phenotype`. **Exclude model-predicted phenotype fields** (per brief).
- Join to `genome` on `genome_id`, filter on quality flags (`genome_status=Complete`
  or good WGS quality, `contigs`, `genome_quality`), download contigs (FASTA) via the
  genome_sequence endpoint / FTPS mirror.
- **Antibiotic selection:** rank antibiotics by count of clean R/S labels and pick the
  **4–5 best-covered with strong genotype links**. Expected shortlist: **erythromycin,
  clindamycin, ciprofloxacin, gentamicin, tetracycline**, plus **oxacillin/cefoxitin**
  (mecA — near-deterministic, great calibration showcase). Final list data-driven.

**Annotation.** Run **AMRFinderPlus** in batch with
`amrfinder -n contigs.fna --organism Staphylococcus_aureus --plus`. Install via
`conda create -n amr -c conda-forge -c bioconda ncbi-amrfinderplus` then `amrfinder -u`
(Docker `ncbi/amr` as fallback). The `--organism` flag is essential — it enables
S. aureus point-mutation detection (gyrA, grlA/parC, rpoB, etc.) and blaZ handling.

**Featurize.** Parse each genome's AMRFinder TSV into a row. **Feature columns = union
across the dataset of** (a) AMR gene symbols (presence/absence, binary) and (b) specific
point mutations (e.g., `gyrA_S84L`). Persist a frozen **feature spec** (ordered column
list + version) so the demo builds identical vectors at inference. This is the Module 01
output-format spec (documented in `docs/DATA_SPEC.md`).

---

## Module 02 — Predictor (will each antibiotic work?)

**Labels.** SIR → binary: **R = resistant (likely to fail)**, **S = susceptible (likely
to work)**. Rule for **I (intermediate)**: default to grouping with R (conservative for
patient safety) but document and test sensitivity to dropping-vs-merging I. If only MIC
given, apply CLSI/EUCAST breakpoints per drug (documented table). One final label per
genome-antibiotic pair.

**De-duplication + grouped split (the rigor centerpiece).**
- Compute pairwise genome similarity with **Mash** (or **skani** for ANI) sketches —
  cheap and scalable.
- **De-dup:** collapse near-identical genomes (e.g., Mash distance < ~0.0002 / ANI
  ≥ 99.98%) to one representative; report how many were collapsed.
- **Grouped split:** single-linkage cluster at a coarser threshold (tune ~0.001–0.005
  Mash distance; **cross-check against MLST clonal complexes** since S. aureus is
  clonal) so each cluster = a genetic group. Assign **whole clusters** to
  train / calibration / hidden-test (GroupKFold-style). **No cluster spans splits** →
  no leakage. Reserve some clusters/CCs *entirely unseen* in training to report the
  honest generalization drop the rubric wants. Justify the threshold in `docs/DECISIONS.md`.

**Baseline model.** One **L2-regularized logistic regression per antibiotic**
(`sklearn`, `class_weight="balanced"`), features = AMR presence-absence matrix. Fast,
CPU, calibratable, and its coefficients map to named genes for honest explanations.

**Deterministic molecular-target gate.** `db/drugs_saureus.csv` maps each drug → class,
molecular target gene(s), and known resistance markers. Rule: **never output "likely to
work" from absence of markers alone** — require the drug's target to be present; if the
target is absent → resistance/no-call as appropriate. (In S. aureus most targets are
intrinsically present, so the gate mainly enforces the "don't infer success from silence"
principle and handles intrinsic cases.)

**Calibration.** Fit the classifier on train; fit **isotonic (or Platt) calibration on
the dedicated calibration split** (never on train or test). Produce **reliability
diagram + Brier score** on the hidden test.

**No-call logic** — return no-call when any of:
1. **Ambiguous probability** — calibrated p within a band around 0.5 (tune, e.g.,
   0.4–0.6) → weak/conflicting evidence.
2. **Out-of-distribution genome** — cheap OOD check: distance to nearest training
   cluster above threshold, or contains AMR genes/mutations never seen in training →
   "unlike training data".
3. **Target gate** fires (target absent / undetermined).
Report **no-call rate and accuracy-on-called** separately per drug.

---

## Module 03 — Decision Report (Streamlit demo)

Upload a FASTA → run pipeline → render per-antibiotic **report cards**:
- Verdict: **likely to fail / likely to work / no-call** (color-coded).
- **Calibrated confidence** bar.
- **Evidence category**, honestly derived:
  - (i) **known resistance gene/mutation detected** (catalog hit from AMRFinderPlus),
  - (ii) **statistical association only** (model coefficient/SHAP, explicitly labeled
    *not proven causal*),
  - (iii) **no known resistance signal found**.
- **Supporting genes/mutations** listed by name.
- Global panels: **held-out performance** (balanced accuracy, per-class recall, F1,
  AUROC, PR-AUC per drug), **reliability plot**, **no-call rate**, and
  **per-genetic-group generalization**.
- **Mandatory banner:** "Research prototype — every result must be confirmed by standard
  laboratory testing. Decision support only; a trained professional makes the decision."
- **Defensive-use statement** + explicit refusal to design/modify organisms.

Speed: cache the trained/calibrated models and the AMRFinder DB; ship 2–3 small demo
genomes precomputed so judges get instant results; live upload runs the real pipeline.

**Optional OpenAI layer (flag-gated, off by default):** turn the *structured* report into
a plain-language clinician summary, **strictly grounded on the structured evidence**
(no new biology), with a hard instruction to defer to lab confirmation. Skip if time-poor.

---

## DL stretch — ESM-2 on AMR proteins (honest baseline comparison)

Extract AMRFinderPlus-flagged protein sequences per genome, embed with **ESM-2**
(`facebook/esm2_t12_35M` or `t30_150M`) on **MPS**, **mean-pool to one vector per
genome**, concatenate with (or replace) the presence-absence features, retrain the
per-antibiotic classifier. Compare against baseline on the **same splits + same
calibration protocol**; report deltas in balanced accuracy / PR-AUC / Brier. Honest
outcome is fine: if it doesn't beat the interpretable baseline, we say so — that's a
rigor win, not a loss.

---

## Metrics reported (all on the hidden grouped-test split)

Balanced accuracy; **recall for R and recall for S separately**; F1; AUROC; **PR-AUC per
drug** (matters under imbalance); **Brier score + reliability diagram**; **no-call rate +
accuracy-on-called**; **generalization broken down by genetic group** (incl. groups
unseen in training). Baseline vs DL deltas side by side.

---

## Parallel execution — 4 workstreams (one per person)

All four start at t=0 against the frozen contracts + synthetic data. Ownership is
**disjoint by file** so git conflicts are near-zero. Full per-person detail in
`docs/subplans/`.

| Person | Focus | Owns | Never blocked because… |
|---|---|---|---|
| **A** | Data & Labels & Drug DB | `acquire.py`, `labels.py`, `data/raw/`, `db/drugs_saureus.csv` | fully independent from t=0 |
| **B** | Annotation & Features | `annotate.py`, `featurize.py`, `data/interim/` | devs on public FASTAs, swaps in A's genomes later |
| **C** | Modeling (rigor core) | `split.py`, `model_baseline.py`, `calibrate.py`, `nocall.py`, `target_gate.py`, `evaluate.py`, `embed_esm.py`, `report.py` | trains on synthetic features until A/B deliver |
| **D** | Demo & Responsible-AI + glue | `app/streamlit_app.py`, `docs/`, optional OpenAI, `Makefile` | renders mock reports until C delivers |

### Integration waves (how the seams connect)
1. **t=0:** foundation on `main`; everyone forks; all build against synthetic/mock.
2. **Wave 1:** B's real `features.parquet` + A's real `labels.csv` land → C swaps
   synthetic → real and retrains.
3. **Wave 2:** C's real report objects + `metrics.json`/plots land → D swaps mock → real.
4. **Wave 3 (final 4h):** freeze; D runs `make all` end-to-end; rehearse demo on
   precomputed held-out genomes (incl. a known **mecA+ MRSA**); write the "how we
   addressed each Responsibility Requirement" section.

**Continuous:** run the self-questioning checklist each wave; log to `DECISIONS.md`/`RISKS.md`.

---

## Top risks & mitigations

- **BV-BRC access friction / label sparsity** → start data pull first; fallback to
  precomputed BV-BRC AMR tables / NCBI Pathogen Detection; pick antibiotics by coverage
  after the pull, don't pre-commit.
- **AMRFinderPlus install/runtime** → conda first, Docker `ncbi/amr` fallback; run
  annotation in parallel; cache TSVs; `--organism Staphylococcus_aureus` mandatory.
- **Data leakage inflating scores** → grouped split by Mash/skani cluster (cross-checked
  vs MLST CC), whole clusters per split, de-dup report — this is the #1 thing judges
  probe.
- **Overclaiming causation** → evidence categories strictly separate catalog hits from
  statistical signal; SHAP never presented as biological proof.

---

## Verification (how we prove it works end-to-end)

1. `make all` runs download → annotate → featurize → split → train → calibrate → evaluate
   reproducibly (checksums match manifest).
2. Confirm **no genome cluster appears in more than one split** (assert in `split.py`;
   print de-dup + leakage report).
3. Reliability diagram + Brier computed on hidden test; confirm calibration curve tracks
   the diagonal.
4. Launch `streamlit run app/streamlit_app.py`, upload a held-out S. aureus FASTA (e.g.,
   a known **MRSA/mecA+** genome), verify: oxacillin → likely-to-fail with (i)
   known-gene evidence citing mecA; a susceptible drug → likely-to-work with target-gate
   satisfied; a weak-evidence case → no-call. Mandatory lab-confirmation banner present.
5. Run DL comparison; confirm the report states baseline-vs-ESM2 deltas honestly.
