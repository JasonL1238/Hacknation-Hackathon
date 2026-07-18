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
    └── DATA_SPEC.md  MODEL_CARD.md  DECISIONS.md  RISKS.md  RESPONSIBLE_AI.md
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
**disjoint by file** so git conflicts are near-zero. Each person reads
[CLAUDE.md](CLAUDE.md) and [docs/DATA_SPEC.md](docs/DATA_SPEC.md) first, then works on
their own branch (`feat/data`, `feat/features`, `feat/model`, `feat/demo`) and merges to
`main` frequently.

### Person A — Data, Labels & Drug Database

> Branch `feat/data`. **Fully independent from t=0** — nobody blocks you, and you block
> Person C's *real* run (they use synthetic labels until you deliver).

**You own (edit freely):** `src/genome_firewall/acquire.py`, `labels.py`; `data/raw/`
(gitignored — commit the manifest, not the genomes); `db/drugs_saureus.csv`.

**Deliverables:**
1. `data/processed/labels.csv` — schema in DATA_SPEC §3. Lab-measured AST only.
2. Quality-filtered genome FASTAs in `data/raw/` + `data/raw/manifest.csv` (genome_id,
   accession, source, checksum, quality flags).
3. `db/drugs_saureus.csv` — schema in DATA_SPEC §5.

**Tasks:**
1. Pull from BV-BRC (`https://www.bv-brc.org/api/`, via `requests` RQL; `p3-*` CLI as
   fallback): query `genome_amr` filtered to *Staphylococcus aureus*, keep rows with a
   **measured** `laboratory_typing_method` (MIC/disk) and a real `resistant_phenotype`.
   **Exclude model-predicted phenotype fields** (challenge rule — critical). Join to
   `genome` on `genome_id`; keep good-quality genomes (genome_status / genome_quality /
   contig count). Download contigs (FASTA).
2. Pick the antibiotics — rank by count of clean R/S labels; choose the **4–5**
   best-covered with strong genotype links. Likely shortlist: erythromycin, clindamycin,
   ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin (mecA showcase). Record
   the choice + counts in `docs/DECISIONS.md`.
3. Labels rule (`labels.py`): SIR → `R`/`S`; default **I → R** (conservative), but
   document and note sensitivity. If only MIC, apply CLSI/EUCAST breakpoints (documented
   table). One label per (genome_id, antibiotic).
4. Drug DB (`db/drugs_saureus.csv`): for each chosen drug fill class, `target_genes`
   (molecular target for the gate), `known_markers`, standardized name.

**Fallbacks:** BV-BRC slow/flaky → use precomputed BV-BRC AMR tables, NCBI Pathogen
Detection, or a documented Kaggle mirror (record license/version/source). Never use
unverified copies without provenance.

**Definition of done:** `labels.csv`, `manifest.csv`, FASTAs, and `drugs_saureus.csv`
exist and validate against DATA_SPEC; antibiotic choice + counts logged in
DECISIONS.md; Person C can drop your `labels.csv` in place of the synthetic one with no
code change.

**Self-questioning before done:** Are any labels model-predicted rather than
lab-measured? Are quality filters documented? Is the I→R decision recorded with its
rationale?

### Person B — Annotation & Feature Pipeline (Module 01)

> Branch `feat/features`. **Never blocked** — dev on a handful of public NCBI
> *S. aureus* FASTAs immediately, swap to Person A's real genomes at integration.

**You own (edit freely):** `src/genome_firewall/annotate.py`, `featurize.py`;
`data/interim/amrfinder/` (per-genome TSVs — gitignored).

**Deliverables:**
1. `data/processed/features.parquet` — DATA_SPEC §1 (binary presence/absence matrix).
2. `data/processed/feature_spec.json` — DATA_SPEC §2 (frozen, ordered column list).

**Tasks:**
1. Install AMRFinderPlus (https://github.com/ncbi/amr): run `make amr-setup`
   (`scripts/setup_amrfinder.sh` — installs into a dedicated conda env `amr` isolated
   from `environment.yml`, downloads the database, falls back to the `ncbi/amr` Docker
   image if conda isn't available). Record the DB version in `feature_spec.json`.
2. Batch runner (`annotate.py`): for each FASTA run
   `amrfinder -n contigs.fna --organism Staphylococcus_aureus --plus -o out.tsv`. The
   `--organism` flag is **mandatory** — it unlocks S. aureus point mutations (gyrA,
   grlA/parC, rpoB) and blaZ handling. Run in parallel; cache TSVs (skip if present) so
   reruns are cheap.
3. Featurize (`featurize.py`): parse each TSV → one row. Feature columns = **union
   across all genomes** of (a) gene symbols and (b) point mutations named as
   `gene_mutation` (e.g. `gyrA_S84L`). Absent = 0. Write `features.parquet` +
   `feature_spec.json` with a version hash of the sorted column list.
4. Inference helper: expose a function that, given a single FASTA, produces a feature
   vector **in `feature_spec.json` column order** (the Streamlit app will call this
   path).

**Fallbacks:** AMRFinderPlus install/runtime trouble → Docker image; or, to unblock
modeling, BV-BRC / NCBI **precomputed** AMRFinderPlus results parsed into the same
matrix schema.

**Definition of done:** `features.parquet` + `feature_spec.json` validate against
DATA_SPEC; the same code path turns one uploaded FASTA into a spec-ordered vector;
Person C can drop your matrix in place of the synthetic one with no code change.

**Self-questioning before done:** Is `--organism Staphylococcus_aureus` set everywhere?
Is the column order frozen and versioned? Does single-genome inference produce a vector
identical in shape/order to the training matrix?

### Person C — Modeling, Split, Calibration, Evaluation, DL stretch (Module 02)

> Branch `feat/model`. **Never blocked** — train on the **synthetic**
> `features.parquet` + `labels.csv` from `_synth.py` until A/B deliver, then swap to
> real (same paths). This workstream is where the hackathon is won: ML rigor &
> calibration is the judged priority.

**You own (edit freely):** `src/genome_firewall/split.py`, `model_baseline.py`,
`calibrate.py`, `nocall.py`, `target_gate.py`, `evaluate.py`, `embed_esm.py`,
`report.py`.

**Deliverables:**
1. `data/processed/splits.json` — DATA_SPEC §4 (grouped, no cluster spans splits).
2. Trained + calibrated per-antibiotic models (pickled under `data/processed/models/`).
3. Report objects via `report.py` — DATA_SPEC §6.
4. `data/processed/metrics.json` + reliability/PR PNGs in `reports/` — DATA_SPEC §7.

**Tasks (in dependency order, but all doable on synthetic first):**
1. De-dup + grouped split (`split.py`): Mash (or skani ANI) sketches → de-dup
   near-identical genomes (~Mash <0.0002 / ANI ≥99.98%), report count collapsed →
   single-linkage cluster at a coarser threshold (tune ~0.001–0.005; cross-check MLST
   clonal complexes) → assign **whole clusters** to train/cal/test. **Assert no cluster
   spans splits.** Hold out some clusters entirely unseen in training. Justify threshold
   in `docs/DECISIONS.md`.
2. Baseline (`model_baseline.py`): one L2-regularized `LogisticRegression`
   (`class_weight="balanced"`) per antibiotic on the presence/absence matrix.
3. Calibration (`calibrate.py`): isotonic (or Platt) fit **on the `cal` split only**;
   reliability diagram + Brier on the **`test` split**.
4. Target gate (`target_gate.py`): read `db/drugs_saureus.csv`; never allow "work" from
   marker-absence alone — require target present; else resistance/no-call.
5. No-call (`nocall.py`): trigger on (a) calibrated p in ~[0.4,0.6], (b) OOD (distance
   to nearest training cluster, or unseen AMR genes/mutations), (c) target gate. Report
   no-call rate + accuracy-on-called.
6. Evidence category (`report.py`): (i) known catalog gene/mutation drove the call, (ii)
   statistical-only (coefficient/SHAP — label as *not proven causal*), (iii) no signal.
   Build the report object per DATA_SPEC §6.
7. Metrics (`evaluate.py`): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC per
   drug, Brier, no-call rate, accuracy-on-called, **per-genetic-group** breakdown incl.
   unseen groups. Write `metrics.json` + PNGs.
8. DL stretch (`embed_esm.py`): ESM-2 (`facebook/esm2_t12_35M`/`t30_150M`) on
   AMRFinder-flagged proteins, mean-pool per genome (MPS), concat/replace features,
   retrain on the **same splits + same calibration**, report deltas honestly. Not
   beating the baseline is a valid, honest result.

**Definition of done:** Splits provably leak-free; calibration curve tracks the diagonal
on held-out; `report.py` emits DATA_SPEC-valid objects; `metrics.json` has per-group
breakdown; DL-vs-baseline deltas computed on identical splits.

**Self-questioning before done:** Could any near-identical genome span train/test? Is
calibration fit only on `cal`? Is any "work" verdict resting on marker-absence without
target-present? Is any SHAP/coefficient presented as biological cause? Do we no-call
enough, or forcing yes/no?

### Person D — Demo, Responsible-AI & Integration/Glue (Module 03)

> Branch `feat/demo`. **Never blocked** — render the **mock** report object from
> `_synth.py` until Person C delivers real ones (same schema, DATA_SPEC §6). You are also
> the **integration owner**: keep `make all` green as synthetic files are replaced by
> real.

**You own (edit freely):** `app/streamlit_app.py`; `docs/` (MODEL_CARD.md,
RESPONSIBLE_AI.md, DECISIONS.md, RISKS.md) — **except** `docs/DATA_SPEC.md` (shared
seam); `Makefile` end-to-end wiring; optional `src/genome_firewall/llm_summary.py`
(flag-gated OpenAI layer).

**Deliverables:**
1. Working Streamlit demo (`streamlit run app/streamlit_app.py`).
2. Responsible-AI docs (MODEL_CARD.md, RESPONSIBLE_AI.md) covering each Responsibility
   Requirement from the brief.
3. Green `make all` end-to-end.

**Tasks:**
1. Report cards (consume DATA_SPEC §6 objects): per antibiotic show verdict
   (fail/work/no-call, color-coded), **calibrated confidence** bar, **evidence
   category** (i/ii/iii with honest wording — statistical ≠ causal), and **supporting
   genes/mutations**.
2. Performance panel (consume `metrics.json` + PNGs): balanced accuracy, per-class
   recall, F1, AUROC, PR-AUC per drug; **reliability plot**; **no-call rate**;
   **per-genetic-group** generalization.
3. Mandatory banner on every result: *"Research prototype — confirm every result with
   standard laboratory testing. Decision support only; a trained professional decides."*
   Plus a **defensive-use statement** and an explicit note that the tool never designs
   or modifies organisms.
4. Live upload path: FASTA upload → call Person B's single-genome feature builder →
   Person C's model + report builder → render. Cache models + AMRFinder DB; ship 2–3
   precomputed demo genomes (incl. a known **mecA+ MRSA**) for instant results.
5. Responsible-AI docs: write MODEL_CARD.md (species/antibiotics covered & NOT covered,
   metrics, calibration, no-call policy, intended use, limitations) and
   RESPONSIBLE_AI.md mapping each brief requirement (defensive-by-construction, honest
   generalization, calibrated confidence + no-call, honest explanations, human
   oversight) to how we address it on held-out data.
6. Own the self-questioning cadence: at each integration wave, run the 7-question
   checklist (see CLAUDE.md) and log answers + evidence in DECISIONS.md; track open
   items in RISKS.md.
7. Optional OpenAI layer (off by default, behind a flag): turn the *structured* report
   into a plain-language clinician summary **strictly grounded on the structured
   evidence** — no invented biology, always defers to lab confirmation. Skip if
   time-poor.

**Definition of done:** App renders calibrated per-antibiotic reports with evidence
categories + mandatory banner on both precomputed and uploaded genomes; performance
panel shows held-out + per-group metrics with a reliability plot; `make all` runs clean
end-to-end; responsible-AI docs complete.

**Self-questioning before done:** Is the lab-confirmation banner impossible to miss?
Does any card imply causation from a statistical feature? Is the no-call state shown as
a legitimate, positive outcome? Does anything in the UI drift toward organism design?

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
