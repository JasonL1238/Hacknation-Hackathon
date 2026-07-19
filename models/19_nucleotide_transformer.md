# Nucleotide / Genomic Language Model Embeddings

## Handoff to the implemented ensemble

For DNABERT-2, the compact sequence inputs already prepared locally are
`data/interim/dnabert2_regions/amr_regions.fasta` and `manifest.csv`; upload those two
files to Kaggle rather than the 6.8 GB raw-genome folder. Use this file/notebook only to
generate one frozen vector per genome. Save the final DataFrame to
`data/processed/dnabert2_embeddings.parquet` with index `genome_id` and numeric columns
`emb_0...emb_n`. Then run `python -m genome_firewall.model_ensemble`; it automatically
tests `dnabert2_only` and `genotype_plus_dnabert2` with the same duplicate-aware protocol
as every other setup. Do not create a new random split or train a separate final head in
the embedding notebook.

> **One-liner:** Embed gene and contig DNA regions with a genomic language model (InstaDeep Nucleotide Transformer or DNABERT-2), pool to one vector per genome, and train a simple head on the same grouped splits.
> **Category:** sequence-DL (DNA) ·
> **Runs on:** Colab GPU (embed) → Colab/local CPU (head) ·
> **Priority:** stretch / optional ·
> **Interpretable:** no

## Why it fits Genome Firewall
A DNA-level language model sees nucleotide context that a protein model cannot: promoter/regulatory regions, synonymous and non-coding variants, and intergenic context around a resistance gene. In principle that could catch resistance signal that lives outside the protein coding sequence AMRFinderPlus flags — the same core value proposition of catching what the presence/absence catalog misses, but at the nucleotide level. In practice the honest expectation is little-to-no gain over targeted protein embeddings (file 17), because ESM-2 already focuses directly on the resistance proteins that carry most of the *S. aureus* signal, and a genomic LM must spread its limited context budget over far more sequence. It belongs here for completeness — to actually *test* whether nucleotide-level context adds anything rather than to assume it does.

## When to prefer it / when to skip it
Treat this as optional and lowest-priority among the sequence models. Only run it after the protein-embedding route (file 17) is in place, and only to answer the specific question "does nucleotide context add signal beyond the flagged proteins?" Skip it as a production candidate unless it beats the logistic-regression baseline on held-out grouped-test Brier and balanced accuracy — and, as with the other sequence models, **report "no gain over the protein embeddings / no gain over the baseline" as a valid, honest, useful result**, since a negative result here justifies not spending GPU budget on DNA models. It is heavier per genome than protein embeddings (long DNA context) and no more interpretable, so the bar for keeping it is high.

## Data interface (the contract this code must respect)
- GPU-ready DNA inputs are `data/interim/dnabert2_regions/amr_regions.fasta` and
  `manifest.csv`. The raw `.fna` genomes and AMRFinder `.tsv` coordinates are needed only
  to regenerate those compact files with `scripts/prepare_dnabert2_regions.py`; they are
  not needed on Kaggle after the compact files have been uploaded. Tokenize the prepared
  regions, embed them, and pool to one vector per `genome_id`.
- Locally: read the cached embeddings as X. Optionally concatenate with `data/processed/features.parquet` presence/absence columns and/or the protein embeddings from file 17; test compositions.
- Read `data/processed/labels.csv`, filter to one antibiotic at a time, map `label` R→1, S→0.
- Read `data/processed/splits.json` for grouped train/cal/test and `cluster_id`; never re-split randomly. Fit the head on **train** only, calibrate on **cal** only, report metrics on **test** only.
- Read `db/drugs_saureus.csv` so the downstream target gate can still veto a "likely-to-work" call when the drug's molecular target is absent.

### Concrete local and Colab paths
- This machine's repository root is `/Users/jasonli/Documents/GitHub/Hacknation-Hackathon`; it currently contains 2,542 `.fna` files under `data/raw/` and matching AMRFinder TSVs under `data/interim/amrfinder/`.
- A Colab runtime cannot read that Mac path. Clone tracked files to `/content/Hacknation-Hackathon`, then copy `data/raw/` and `data/interim/amrfinder/` to `/content/drive/MyDrive/Hacknation-Hackathon-sequence-data/` with the same directory structure.
- Generated notebook code must define separate `REPO_ROOT` and `SEQUENCE_ROOT` variables, allow environment-variable overrides, validate matching `<genome_id>.fna`/`.tsv` pairs and overlap with labels/splits, and stop clearly if files are missing.
- **Relative-path option:** when running locally from the repository root, use `data/raw/`, `data/interim/amrfinder/`, `data/processed/`, and `db/` directly. In Colab, those relative sequence paths work only after the `.fna` and `.tsv` files have actually been copied beneath `/content/Hacknation-Hackathon/data/`; cloning alone does not include them. The notebook must change to the repository root and validate file counts before embedding.

## Adversarial checks it must survive
- **Context-length / coverage honesty:** Genomic LMs have hard context limits (a few kb to ~tens of kb depending on the model and tokenizer). You physically cannot embed a whole *S. aureus* genome in one pass — you must window/tile and pool, and how you choose windows biases what the model sees. State the tiling scheme and confirm the flagged-resistance regions are actually inside the embedded windows, or the model is blind to the very signal it is meant to add.
- **No leakage (Rule 1):** Embedding is per-genome and label-free, but the head must be fit on train only, calibrated on cal only, with any head hyperparameter search via GroupKFold on `cluster_id` inside train. Confirm no `cluster_id` spans splits.
- **Clonal memorization:** DNA embeddings of a clonal lineage are highly similar, so the head can track lineage rather than mechanism; report per-genetic-group metrics including unseen clusters and compare the drop against the baseline.
- **Calibration (Rule 2):** Calibrate on `cal`; report reliability + Brier on `test`.
- **Honest explanations (Rule 5):** Not interpretable — embedding-dimension weights and attention are statistical signal, not biological causation; defer to the flagged-gene catalog for human-readable evidence.
- **Honest comparison protocol:** Use the SAME grouped splits and the SAME calibration protocol as the baseline, and report deltas (balanced accuracy, PR-AUC, Brier) vs the logistic-regression presence/absence baseline AND vs the ESM-2 protein embeddings — the latter comparison is the whole point of running this model.
- **No forced calls (Rule 3):** Feed calibrated probabilities into the no-call band; never threshold at 0.5.

## Hyperparameters worth sweeping
- **Backbone:** InstaDeep Nucleotide Transformer variants (e.g. `InstaDeepAI/nucleotide-transformer-*`) vs DNABERT-2 — different tokenizers (k-mer vs BPE) and context lengths.
- **Window/tiling scheme:** flagged-region-only vs wider contig windows; window size and stride; how windows are pooled to a genome vector (mean / max / attention).
- **Feature composition:** DNA-embeddings-only vs `concat(DNA, protein embeddings)` vs `concat(DNA, presence/absence)` — test whether DNA adds anything on top.
- **Head:** logistic regression (`C` over `np.logspace(-3, 2, 12)`, `class_weight="balanced"`) or gradient boosting (`scale_pos_weight` for imbalance); optional PCA before the head.
- **GPU-memory knobs:** batch size, sequence length / truncation, mixed precision — DNA context is memory-hungry, so document the memory ceiling on Colab.
- Cache embeddings to disk so head sweeps never re-run the GPU step.

## Calibration & no-call handling
Calibrate the head like every other model: `CalibratedClassifierCV(cv="prefit")` (or isotonic/Platt) fit on the **cal** split; prefer isotonic if cal is large enough, else sigmoid/Platt. The calibrated probability drives no-call: return `no-call` in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution relative to training clusters (embedding distance can serve as the OOD signal), or when the target gate fires (drug target absent → do not claim "likely to work" from marker absence alone).

## Metrics to report
On the held-out grouped **test** split, and broken down **per genetic group** (including groups unseen in training): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report every number as a **delta vs the logistic-regression presence/absence baseline AND vs the ESM-2 protein embeddings** — a null delta against the protein embeddings is the expected, and fully reportable, headline result.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

I want to use a NUCLEOTIDE / GENOMIC LANGUAGE MODEL (InstaDeep Nucleotide Transformer or DNABERT-2) to embed DNA regions, pool per genome, and train a simple head. This runs in TWO stages in GOOGLE COLAB: (1) a GPU stage that computes frozen DNA embeddings, and (2) a CPU stage in the same notebook that trains and calibrates the head. Write complete, runnable Colab notebook cells (transformers, torch, scikit-learn, pandas, numpy, matplotlib), including Google Drive mounting and path validation.

DATA CONTRACT (files already exist on disk):
- PATHS: on this Mac, `REPO_ROOT=/Users/jasonli/Documents/GitHub/Hacknation-Hackathon` and `SEQUENCE_ROOT=REPO_ROOT`. In Colab, use `REPO_ROOT=/content/Hacknation-Hackathon` for the Git clone and `SEQUENCE_ROOT=/content/drive/MyDrive/Hacknation-Hackathon-sequence-data` for the untracked FASTA/AMRFinder data copied from this Mac. Mount Google Drive in Colab. Define both roots as `pathlib.Path` values with environment-variable overrides `GENOME_FIREWALL_ROOT` and `GENOME_FIREWALL_SEQUENCE_ROOT`; resolve tracked tables relative to REPO_ROOT and sequence inputs relative to SEQUENCE_ROOT. Fail with a clear error if required files or genome-ID matches are missing.
- RELATIVE PATHS: if all sequence folders have been copied beneath REPO_ROOT, change the working directory to REPO_ROOT and use `data/raw`, `data/interim/amrfinder`, `data/processed`, and `db` as relative paths. In Colab, verify that `data/raw` contains `.fna` files and `data/interim/amrfinder` contains matching `.tsv` files; a Git clone by itself is insufficient.
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.
- SEQUENCE_ROOT/data/interim/dnabert2_regions/amr_regions.fasta and manifest.csv: compact
  targeted AMR DNA regions already extracted locally from matching raw genomes and
  AMRFinder coordinates. Use these directly on Kaggle. Raw `.fna`/`.tsv` files are needed
  only if regenerating this compact dataset.

STAGE 1 (COLAB GPU) - compute embeddings:
- Use a Hugging Face genomic LM. Make the checkpoint a parameter and support InstaDeepAI Nucleotide Transformer variants and DNABERT-2 (different tokenizers: k-mer vs BPE, different context lengths).
- Genomic LMs have HARD context limits and you cannot embed a whole genome at once: implement WINDOW/TILING (window size + stride as parameters), embed each window, and pool windows to ONE fixed-length vector per genome_id (mean/max/attention pooling switchable). Ensure the flagged-resistance regions actually fall inside the embedded windows and say so.
- Batch on GPU (cuda), use no_grad (frozen backbone). Document the GPU memory ceiling and use mixed precision / truncation as needed. This is the GPU-heavy step.
- Save the result as `data/processed/dnabert2_embeddings.parquet`, indexed by genome_id
  (numeric embedding columns), so the implemented ensemble finds it automatically. Cache
  it so re-runs are cheap.

STAGE 2 (LOCAL CPU) - head + calibration + evaluation:
1. Load the cached per-genome DNA embeddings, labels.csv, splits.json, drugs_saureus.csv. Support feature compositions: DNA-embeddings only, concat with presence/absence, and (if available) concat with ESM-2 protein embeddings - make it a parameter and run all of them.
2. Train ONE head PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
3. Fit the head on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
4. NEVER re-split randomly and NEVER let a cluster span splits - always use splits.json. If you need internal validation for head hyperparameters, use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
5. Handle class imbalance with class_weight="balanced" (logistic) or scale_pos_weight (gradient boosting). Do NOT use SMOTE or synthetic oversampling.
6. Head options: sklearn LogisticRegression (sweep C over np.logspace(-3,2,12)) OR LightGBM/XGBoost. Optionally PCA the embeddings first. Make head choice a parameter.
7. Calibrate the fitted head with CalibratedClassifierCV(cv="prefit") on the cal split (try isotonic and sigmoid; pick per antibiotic by cal-split Brier).
8. Emit calibrated probabilities and implement a no-call rule: return "no-call" when calibrated p is in ~0.4-0.6, when the genome's embedding is far from all training-cluster embeddings (OOD), or when the target gate fires (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id) including clusters unseen in training, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic.
- IMPORTANT: also load reports/metrics_logreg_l2.json (logistic-regression presence/absence baseline) and reports/metrics_esm2_embeddings.json (ESM-2 protein embeddings) if present, and report every metric as a DELTA vs BOTH. The key question is whether nucleotide context adds anything over the protein embeddings - a null/negative delta is a valid, honest, useful result and should be reported plainly.
- This model is NOT interpretable: embedding-dimension weights and attention are statistical signal, NOT biological causation - state this and defer to the flagged-gene catalog for human-readable evidence.
- Save per-antibiotic metrics (and per-composition) to a dict and to JSON (e.g. reports/metrics_nucleotide_transformer.json). Print a clean summary table (rows = antibiotics, columns = metrics + deltas vs baseline and vs protein embeddings).

Do not fabricate data; load only the files described. Provide the full script for both stages.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
