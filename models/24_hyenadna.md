# HyenaDNA (long-range genomic model)

> **One-liner:** A Hyena-operator genomic model with single-nucleotide tokenization and ultra-long context that embeds DNA regions for per-genome classification.
> **Category:** sequence-DL (DNA) ·
> **Runs on:** Colab GPU (embed) → Colab/local CPU (head) ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
HyenaDNA (`LongSafari/hyenadna-*`, e.g. `hyenadna-medium-450k-seqlen`) uses implicit long
convolutions instead of attention, giving it **single-nucleotide resolution** at **very
long context** (tens of thousands to ~1M bp). Two properties matter here: single-base
tokenization means it can, in principle, represent a **point mutation directly** (the
exact base behind `gyrA_S84L` / `grlA_S80F`), and long context means it can read a whole
gene plus its regulatory neighborhood in one pass — signal the presence/absence matrix and
a protein model cannot express. It is the most "reads the raw genome" option in the
catalog, and an honest test of whether that resolution buys anything.

## When to prefer it / when to skip it
Prefer it when you want maximal nucleotide-resolution / long-range coverage — e.g. probing
whether resistance signal lives in point mutations or regulatory regions across a long
locus. **Skip or deprioritize it** if the presence/absence baseline and ESM-2/DNABERT-2
already explain the labels: HyenaDNA is pretrained on the **human genome**, so it carries a
real **domain-shift penalty on a bacterial genome** — flag this as the central caveat and
expect it may underperform DNABERT-2 (which is multi-species) here. As with all DL, not
beating the interpretable baseline is a valid, reportable result.

## Data interface (the contract this code must respect)
Consumes **DNA sequence**, not `features.parquet`:
- Input per genome: assembled contigs FASTA in `data/raw/` for each `genome_id`. Use the
  **AMRFinderPlus-flagged gene loci** (coordinates in `data/interim/amrfinder/<id>.tsv`,
  with flanks) — HyenaDNA's long context also allows feeding **larger windows / whole
  contigs** if you want to exploit its range.
- Targets: `data/processed/labels.csv` (per-antibiotic R/S per `genome_id`).
- Splits: `data/processed/splits.json` (`train`/`cal`/`test` + `cluster_id`, grouped).
- Target gate reference: `db/drugs_saureus.csv`.
- **Protocol:** embed each region with HyenaDNA, **mean-pool to one vector per genome**,
  train one **head per antibiotic** on `train`, calibrate on `cal`, evaluate on `test`.
  No `cluster_id` spans splits. Cache embeddings so head sweeps are cheap and CPU-only.

### Concrete local and Colab paths
- This machine's repository root is `/Users/jasonli/Documents/GitHub/Hacknation-Hackathon`; it currently contains 2,542 `.fna` files and 2,542 matching AMRFinder TSVs.
- A Colab runtime cannot read that Mac path. Use `/content/Hacknation-Hackathon` for the clone and copy `data/raw/` plus `data/interim/amrfinder/` to `/content/drive/MyDrive/Hacknation-Hackathon-sequence-data/`, preserving their relative paths.
- Generated notebook code must keep `REPO_ROOT` and `SEQUENCE_ROOT` separate, support environment-variable overrides, filter AMRFinder rows to `Type == AMR`, match contig IDs exactly, validate genome-ID coverage against labels/splits, and fail clearly on missing files.
- **Relative-path option:** when running locally from the repository root, use `data/raw/`, `data/interim/amrfinder/`, `data/processed/`, and `db/` directly. In Colab, those relative sequence paths work only after the `.fna` and `.tsv` files have actually been copied beneath `/content/Hacknation-Hackathon/data/`; cloning alone does not include them. The notebook must change to the repository root and validate file counts before embedding.

## Adversarial checks it must survive
- **Domain shift (the headline caveat):** human-pretrained → bacterial inference. Report
  results next to DNABERT-2 (multi-species) and ESM-2; if it underperforms, say why.
- **Leakage (rule 1):** embeddings are features; grouped split governs. Whole
  `cluster_id`s per split; any head val set from `train` via GroupKFold only.
- **Clonal memorization:** long-context DNA can encode lineage. Judge on unseen-cluster
  per-group metrics and Brier, not aggregate accuracy.
- **Calibration (rule 2):** calibrate the head on `cal` (Platt/isotonic/temperature);
  Brier + reliability on `test`.
- **Honest comparison:** same grouped splits + same calibration as the baseline; report
  deltas. No gain is an honest outcome.
- **Honest explanation (rule 5):** no trustworthy causal attribution; user-facing
  evidence comes from the catalog/target gate.
- **Generalization (rule 6):** per-group incl. unseen clusters; report the drop.

## Hyperparameters worth sweeping
- Checkpoint / context length: `hyenadna-tiny-1k` … `hyenadna-medium-450k-seqlen` (bigger
  context vs GPU memory/speed).
- Window definition: gene-locus+flank vs large window vs whole contig; flank size.
- Pooling: mean vs max vs attention over the per-base/per-region embeddings.
- Extraction layer.
- The **head** (cheap, sweep locally): logistic-regression `C` or a gradient-boosted head;
  embeddings concatenated **with** vs **replacing** the presence/absence features.

## Calibration & no-call handling
Freeze HyenaDNA, produce per-genome embeddings, train the head on `train`, calibrate on
`cal`, and route calibrated p through the no-call logic (ambiguous band ~0.4–0.6 →
`no-call`, plus OOD and target-gate no-calls). Report no-call rate + accuracy-on-called on
`test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability
diagram**, no-call rate + accuracy-on-called — on the held-out grouped **test** split and
per genetic group (including unseen clusters). Always report the **delta vs the logistic
regression baseline, vs ESM-2, and vs DNABERT-2** on identical splits.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S), with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

I want to test HyenaDNA (LongSafari/hyenadna-*, a long-range genomic model with single-nucleotide tokenization; note it is pretrained on the HUMAN genome, so there is a domain-shift caveat on a bacterial genome) as a sequence-DL model. The environment is GOOGLE COLAB with a GPU for the embedding step; the classifier head can run on CPU in the same notebook. Write complete, runnable Colab notebook cells, including Google Drive mounting and path validation.

DATA CONTRACT (assume these exist, paths as given):
- PATHS: on this Mac, `REPO_ROOT=/Users/jasonli/Documents/GitHub/Hacknation-Hackathon` and `SEQUENCE_ROOT=REPO_ROOT`. In Colab, mount Google Drive, use `REPO_ROOT=/content/Hacknation-Hackathon`, and use `SEQUENCE_ROOT=/content/drive/MyDrive/Hacknation-Hackathon-sequence-data`. Define both as `pathlib.Path` values with environment-variable overrides `GENOME_FIREWALL_ROOT` and `GENOME_FIREWALL_SEQUENCE_ROOT`. Resolve tracked tables from REPO_ROOT and large sequence inputs from SEQUENCE_ROOT; validate paths and genome-ID overlap before embedding.
- RELATIVE PATHS: if all sequence folders have been copied beneath REPO_ROOT, change the working directory to REPO_ROOT and use `data/raw`, `data/interim/amrfinder`, `data/processed`, and `db` as relative paths. In Colab, verify that `data/raw` contains `.fna` files and `data/interim/amrfinder` contains matching `.tsv` files; a Git clone by itself is insufficient.
- SEQUENCE_ROOT/data/raw/<genome_id>.fna: assembled contigs (FASTA) per genome. genome_id is a string like "1280.1234".
- SEQUENCE_ROOT/data/interim/amrfinder/<genome_id>.tsv: per-genome AMRFinderPlus output. Use only rows with `Type == AMR`; coordinates are 1-based inclusive (`Contig id`, `Start`, `Stop`, `Strand`) and the contig ID must match the FASTA record ID exactly.
- REPO_ROOT/data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- REPO_ROOT/data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- REPO_ROOT/db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

STEP 1 - EMBED (GPU):
- For each genome, extract the DNA of the AMRFinderPlus-flagged gene loci from its FASTA using the TSV coordinates, with a configurable flank (default ~200 bp). Also support a large-window / whole-contig mode to exploit HyenaDNA's long context.
- Embed each region with a HyenaDNA checkpoint (make the checkpoint / context length configurable, e.g. hyenadna-medium-450k-seqlen), then MEAN-POOL to a single vector PER GENOME. Support max/attention pooling and layer selection as options.
- Cache the per-genome embedding matrix to disk (.npy + genome_id index) so the head can be trained locally on CPU without re-running the GPU step.

STEP 2 - HEAD + EVALUATION (local CPU):
- Train ONE classifier head PER antibiotic. Default head: logistic regression (class_weight="balanced"); also support a gradient-boosted head. Support concatenating embeddings WITH the binary presence/absence matrix (data/processed/features.parquet, index genome_id, int8 columns) vs embeddings alone (flag).
- Fit the head on TRAIN only. Fit calibration (Platt or isotonic) on CAL only. Report ALL metrics on TEST only.
- NEVER re-split randomly and NEVER let a cluster_id span splits - always use splits.json. Any internal validation set comes from TRAIN via GroupKFold on cluster_id, never cal/test.
- Do NOT use synthetic oversampling.

REPORTING:
- On TEST, per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, reliability diagram. Also no-call rate + accuracy-on-called, where "no-call" = calibrated p in ~0.4-0.6 (stub OOD and target-gate no-calls as hooks).
- Report metrics PER GENETIC GROUP, separating test clusters SEEN vs UNSEEN in training, and print the drop on unseen clusters.
- Because HyenaDNA is human-pretrained, explicitly note the domain-shift caveat in the output and make results directly comparable to a logistic-regression baseline on the same splits.
- Save per-antibiotic metrics to a dict -> JSON and print a summary table.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate data. HyenaDNA gives no trustworthy causal attribution, so never present its signal as biological causation. Output clean, self-contained scripts (an embedding script and a head/eval script).
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
