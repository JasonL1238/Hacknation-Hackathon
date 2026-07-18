# DNABERT-2 (genomic DNA language model)

> **One-liner:** A BPE-tokenized transformer pretrained on multi-species genomes that turns DNA regions into embeddings you can pool per genome and classify.
> **Category:** sequence-DL (DNA) ·
> **Runs on:** Kaggle GPU (embed) → local CPU (head) ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
DNABERT-2 (`zhihan1996/DNABERT-2-117M`) is pretrained on genomes from **many species,
including prokaryotes**, which makes it a much better domain fit for *S. aureus* than
human-only DNA models. Working at the DNA level lets it see signal that a protein model
(ESM-2) and the binary presence/absence matrix both miss: **synonymous and non-coding
variants, promoter/regulatory changes, and point mutations at nucleotide resolution**
(e.g. the exact substitution behind `gyrA_S84L`). Its BPE tokenizer keeps sequences short
enough that a short gene region fits comfortably in context. The honest role here is a
stretch experiment: does nucleotide-level context beat the catalog-driven baseline, or
just add cost?

## When to prefer it / when to skip it
Prefer it over ESM-2 when you suspect resistance is driven by variants **outside the
translated protein** the catalog flags — regulatory up-mutations, novel alleles, or
mutations in genes AMRFinderPlus does not translate. Skip it (or keep it a low-priority
stretch) if the presence/absence baseline and ESM-2 already explain the labels, since on
this clonal, catalog-rich data a heavier DNA model usually will not beat logistic
regression — and **reporting that it doesn't is a valid result**. It is also a black box:
never use it as the user-facing explanation; that comes from the AMR catalog + target gate.

## Data interface (the contract this code must respect)
Unlike the tabular models, this consumes **DNA sequence**, not `features.parquet`:
- Input sequence per genome: the assembled contigs FASTA in `data/raw/` for each
  `genome_id`. Restrict to the **AMRFinderPlus-flagged gene loci** (use the start/stop
  coordinates in the per-genome AMRFinder TSV under `data/interim/amrfinder/`, with a
  small flank to capture promoters) — or, as a heavier variant, tile whole contigs.
- Targets: `data/processed/labels.csv` — per antibiotic, the R/S label per `genome_id`.
- Splits: `data/processed/splits.json` — `train`/`cal`/`test` + `cluster_id` (grouped).
- Target gate reference: `db/drugs_saureus.csv`.
- **Protocol:** embed each region with DNABERT-2, **mean-pool to one vector per genome**,
  then train one **head per antibiotic** on `train`, calibrate the head on `cal`, evaluate
  on `test`. Never let a `cluster_id` span splits. Cache embeddings to disk so head sweeps
  are cheap and CPU-only.

## Adversarial checks it must survive
- **Leakage (rule 1):** embeddings are just features — the grouped split still governs
  everything. Assign whole `cluster_id`s to one split; any early-stopping val set for the
  head comes from `train` via GroupKFold, never from `cal`/`test`.
- **Clonal memorization:** a DNA model can encode lineage rather than mechanism and look
  strong on seen clusters. Judge it on the **unseen-cluster** per-group breakdown and on
  Brier, not aggregate accuracy.
- **Calibration (rule 2):** embeddings + head are not calibrated by default — fit
  Platt/isotonic (or temperature) on `cal`, report Brier + reliability on `test`.
- **Honest comparison:** run the **same grouped splits + same calibration** as the
  logistic-regression baseline and ESM-2, and report deltas (balanced accuracy, PR-AUC,
  Brier). No gain over the baseline is an honest, reportable outcome — say so plainly.
- **Honest explanation (rule 5):** no trustworthy per-nucleotide causal attribution.
  Supporting genes/mutations shown to users come from the catalog/target gate, not from
  DNABERT-2 saliency.
- **Generalization (rule 6):** report per genetic group incl. unseen clusters; expect a
  drop; report it.

## Hyperparameters worth sweeping
- Region definition: gene-locus-only vs gene+flank vs whole-contig tiling; flank size.
- Pooling: mean vs max vs attention pooling over token/region embeddings.
- Layer to extract embeddings from (last vs a mid layer).
- The **head** (this is the cheap part, sweep locally): logistic regression `C`, or a
  gradient-boosted head; concatenate embeddings **with** the presence/absence features vs
  **replace** them — test both.
- Max token length / sequence chunking; batch size (GPU memory only, not model quality).

## Calibration & no-call handling
Freeze DNABERT-2, produce per-genome embeddings, train the head on `train`, then calibrate
the head's probabilities on `cal` (Platt/isotonic; temperature if the head is a neural
net). Feed calibrated p into the no-call logic: ambiguous band (~0.4–0.6) → `no-call`,
plus the pipeline's OOD and target-gate no-calls. Report no-call rate + accuracy-on-called
on `test`.

## Metrics to report
Balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability
diagram**, no-call rate + accuracy-on-called — on the held-out grouped **test** split and
per genetic group (including unseen clusters). Always report the **delta vs the logistic
regression baseline and vs ESM-2** on identical splits.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely resistant (R) or susceptible (S), with a calibrated confidence. It only predicts and explains resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split), not raw accuracy.

I want to test DNABERT-2 (zhihan1996/DNABERT-2-117M, a BPE-tokenized DNA language model pretrained on multi-species genomes) as a sequence-DL model. The environment is Kaggle with a GPU for the embedding step; the classifier head runs locally on CPU. Write complete, runnable Python.

DATA CONTRACT (assume these exist, paths as given):
- data/raw/<genome_id>.fna: assembled contigs (FASTA) per genome. genome_id is a string like "1280.1234".
- data/interim/amrfinder/<genome_id>.tsv: per-genome AMRFinderPlus output with the coordinates (contig, start, stop, strand) of flagged AMR gene loci.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S}, source, method. One row per (genome_id, antibiotic). ~4-6 antibiotics (erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name.

STEP 1 - EMBED (GPU):
- For each genome, extract the DNA of the AMRFinderPlus-flagged gene loci from its FASTA using the TSV coordinates, adding a configurable flank (default ~200 bp) to capture promoters. (Also support a "whole-contig tiling" mode as an alternative.)
- Embed each region with DNABERT-2, then MEAN-POOL to a single fixed-length vector PER GENOME. Support max/attention pooling as options and an option to pick the extraction layer.
- Cache the per-genome embedding matrix to disk (e.g. .npy + a genome_id index) so the head can be trained/re-swept locally on CPU without re-running the GPU step.

STEP 2 - HEAD + EVALUATION (local CPU):
- Train ONE classifier head PER antibiotic (loop over antibiotics). Default head: logistic regression (class_weight="balanced"); also support a gradient-boosted head. Support concatenating the embeddings WITH a binary presence/absence feature matrix (data/processed/features.parquet, index genome_id, int8 columns) vs using embeddings alone - make this a flag.
- Fit the head on the TRAIN split ONLY. Fit probability calibration (Platt or isotonic) on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
- NEVER re-split randomly and NEVER let a cluster_id span splits - always use splits.json. If the head needs an internal validation set, carve it from TRAIN via GroupKFold on cluster_id, never from cal/test.
- Do NOT use synthetic oversampling.

REPORTING:
- On TEST, per antibiotic: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, reliability diagram. Also no-call rate and accuracy-on-called, where "no-call" = calibrated p in the ambiguous band ~0.4-0.6 (leave OOD and target-gate no-calls as stub hooks).
- Report metrics PER GENETIC GROUP, separating test clusters SEEN vs UNSEEN in training, and print the drop on unseen clusters.
- Save per-antibiotic metrics to a dict -> JSON and print a summary table.

Do NOT introduce data leakage, do NOT re-split randomly, and do NOT fabricate data. DNABERT-2 gives no trustworthy causal attribution, so never present its signal as biological causation. Output clean, self-contained scripts (an embedding script and a head/eval script).
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
