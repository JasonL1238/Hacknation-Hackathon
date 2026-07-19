# ESM-2 Fine-Tuning (Head-Only / LoRA)

> **One-liner:** Fine-tune an ESM-2 protein language model end-to-end on the per-antibiotic R/S label — training only a classification head or low-rank LoRA adapters over a frozen backbone — then temperature-scale the logits for calibration.
> **Category:** sequence-DL ·
> **Runs on:** Colab GPU ·
> **Priority:** stretch ·
> **Interpretable:** no

## Why it fits Genome Firewall
Fine-tuning lets ESM-2 adapt its representations to the specific resistance signal rather than relying on generic pretraining, so in principle it can pick up subtle mutated-variant patterns that a frozen-embedding head (file 17) averages away. Its one legitimate edge over presence/absence is the same as the frozen route — catching resistance from a *mutated gene variant* AMRFinderPlus's catalog does not flag — but with the model free to reshape its features around that signal. The catch is that this is the heaviest and riskiest option in the whole model roster: with only a few hundred grouped genomes, a fine-tuned protein LM will happily memorize clonal lineage structure and overfit, which is exactly what a calibration-first project must not do. It earns its place only as a stretch experiment measured honestly against the cheaper baselines.

## When to prefer it / when to skip it
Only reach for this after the frozen-embeddings route (file 17) has been tried and either plateaued or shown a specific mutated-variant signal that full fine-tuning might sharpen. Prefer LoRA/PEFT or head-only fine-tuning over full-backbone fine-tuning always, given the data size. **Skip it as the production model unless it beats both the logistic-regression baseline AND the frozen-embeddings head on held-out grouped-test Brier and balanced accuracy by a margin that survives the per-group breakdown** — and treat "it did not beat them" as a valid, honest, reportable outcome, not a failure to hide. Given the overfitting risk, the burden of proof on this model is higher than on any other.

## Data interface (the contract this code must respect)
- Input is `data/interim/esm2_proteins/<genome_id>.faa` (the same protein set used in file 17), tokenized with the ESM-2 tokenizer. Create or refresh these files locally with `python scripts/prepare_esm2_fastas.py`. If a genome has multiple flagged proteins, either fine-tune per protein and pool, or feed a concatenated/aggregated representation — state which.
- Read `data/processed/labels.csv`, filter to one antibiotic at a time, map `label` R→1, S→0. Train ONE fine-tuned model PER antibiotic.
- Read `data/processed/splits.json` for grouped train/cal/test and `cluster_id`; never re-split randomly. Train on **train** only; carve any early-stopping validation set out of **train** via GroupKFold on `cluster_id` (never touch `cal` or `test`); temperature-scale on **cal** only; report metrics on **test** only.
- Read `db/drugs_saureus.csv` so the downstream target gate can still veto a "likely-to-work" call when the drug's molecular target is absent.

### Concrete local and Colab paths
- This machine's repository root is `/Users/jasonli/Documents/GitHub/Hacknation-Hackathon`.
- A Colab runtime cannot read that Mac path. Clone the tracked repository to `/content/Hacknation-Hackathon`, mount Google Drive, and copy the locally generated `data/interim/esm2_proteins/` directory to `/content/drive/MyDrive/Hacknation-Hackathon-sequence-data/data/interim/esm2_proteins/`.
- Generated notebook code must define `REPO_ROOT` and `SEQUENCE_ROOT` separately, allow environment-variable overrides, validate paths and genome-ID overlap before training, and recover `genome_id` from the prefix before the first `|` in every protein FASTA record ID.
- **Relative-path option:** when running locally from the repository root, `data/interim/esm2_proteins/`, `data/processed/`, and `db/` are valid relative paths. In Colab, relative paths work only after the protein directory has actually been copied into `/content/Hacknation-Hackathon/data/interim/esm2_proteins/`; cloning alone does not provide it because `data/interim/*` is ignored by Git. The notebook must `%cd /content/Hacknation-Hackathon` (or use `os.chdir`) and verify the files before using relative paths.

## Adversarial checks it must survive
- **No leakage (Rule 1):** The early-stopping validation set MUST come from GroupKFold on `cluster_id` within train — a random validation split would let the same clone appear in train and val and give a falsely optimistic stop point. `cal` and `test` stay untouched during training. Confirm no `cluster_id` spans splits.
- **Overfitting / clonal memorization (the central risk):** A few hundred genomes is tiny for a protein LM. Freeze the backbone (train only the head) or use low-rank LoRA adapters, use aggressive dropout and early stopping, and compare the unseen-cluster metric drop directly against the baseline — a large fine-tuned-only drop is direct evidence of lineage memorization, and must be reported, not smoothed over.
- **Calibration (Rule 2):** Fine-tuned deep classifiers are notoriously over-confident. Temperature-scale the logits on `cal` and report reliability + Brier on `test`; do not trust raw softmax probabilities.
- **Honest explanations (Rule 5):** This model is not interpretable — attributions (e.g. attention or gradient saliency over residues) are statistical signal, never biological causation, and must be labeled as such. Fall back to the flagged-gene catalog for the human-readable evidence.
- **Honest comparison protocol:** Use the SAME grouped splits and the SAME calibration protocol (here: temperature scaling on cal) as the baseline, and report deltas (balanced accuracy, PR-AUC, Brier) vs the logistic-regression presence/absence baseline and vs the frozen-embeddings head.
- **No forced calls (Rule 3):** Feed calibrated probabilities into the no-call band; never threshold hard at 0.5.

## Hyperparameters worth sweeping
- **Adaptation strategy:** head-only (backbone frozen) vs LoRA/PEFT (backbone frozen, adapters trained). Avoid full-backbone fine-tuning on this data size.
- **LoRA rank** (e.g. 4, 8, 16) and which projection matrices adapters attach to.
- **Learning rate** (small, e.g. `1e-5`–`5e-4`; head can take a higher lr than adapters), **epochs** (few, with early stopping), **dropout** (raise it), weight decay.
- **Backbone size:** start with `facebook/esm2_t12_35M_UR50D` or `t30_150M`; only go to `t33_650M` if GPU memory allows and smaller models justify it.
- **Class imbalance:** weighted cross-entropy (per-class weights) — do NOT synthetically oversample across the grouped structure.
- Early-stopping patience and the GroupKFold-from-train validation fold used to trigger it.

## Calibration & no-call handling
Calibrate by **temperature scaling**: fit a single scalar temperature on the **cal** split logits (minimize NLL/Brier), then apply it at inference. Optionally follow with isotonic/Platt on cal if temperature alone under-calibrates. The calibrated probability drives no-call: return `no-call` in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution relative to training clusters, or when the target gate fires (drug target absent → do not claim "likely to work" from marker absence alone).

## Metrics to report
On the held-out grouped **test** split, and broken down **per genetic group** (including groups unseen in training): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report every number as a **delta vs the logistic-regression presence/absence baseline** (and vs the frozen-embeddings head from file 17). Because overfitting is the primary risk, foreground the seen-vs-unseen-cluster gap.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

I want to FINE-TUNE an ESM-2 protein language model (head-only or LoRA/PEFT) end-to-end on the per-antibiotic R/S label. This is a stretch experiment on a SMALL dataset with HIGH overfitting risk, so favor freezing the backbone and training only a head or low-rank LoRA adapters. This runs on a GOOGLE COLAB GPU (cuda). Write complete, runnable Colab notebook cells (transformers, peft, torch, scikit-learn, pandas, numpy, matplotlib), including Google Drive mounting and path validation.

DATA CONTRACT (files already exist on disk):
- PATHS: on this Mac, `REPO_ROOT=/Users/jasonli/Documents/GitHub/Hacknation-Hackathon` and `SEQUENCE_ROOT=REPO_ROOT`. In Colab, use `REPO_ROOT=/content/Hacknation-Hackathon` for the Git clone and `SEQUENCE_ROOT=/content/drive/MyDrive/Hacknation-Hackathon-sequence-data` for the large untracked data copied from this Mac. At the top of the notebook, mount Google Drive when running in Colab, define both roots as `pathlib.Path` values (environment-variable overrides `GENOME_FIREWALL_ROOT` and `GENOME_FIREWALL_SEQUENCE_ROOT`), and fail with a clear missing-path error rather than silently using fabricated data.
- RELATIVE PATHS: if all required folders have been copied beneath the repository, first change the working directory to REPO_ROOT and use `data/interim/esm2_proteins`, `data/processed`, and `db` as relative paths. In Colab, cloning does not include `data/interim/esm2_proteins`; confirm that directory exists and contains `.faa` files before training. Do not assume a relative path exists merely because the repository was cloned.
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.
- SEQUENCE_ROOT/data/interim/esm2_proteins/<genome_id>.faa: one prepared FASTA per genome containing translated AMRFinderPlus rows with Type == AMR. Record IDs begin `<genome_id>|`. The directory also contains `all_amr_proteins.faa` and `manifest.csv` with columns genome_id, protein_count, fasta_file. These are generated locally by `python scripts/prepare_esm2_fastas.py`. Tokenize these amino-acid sequences with ESM-2; do not feed nucleotide `.fna` files to ESM-2. If a genome has multiple proteins, fine-tune per protein and pool genome-level logits, or explicitly state another aggregation strategy.

MODEL:
- Use a Hugging Face ESM-2 checkpoint (facebook/esm2_t12_35M_UR50D or facebook/esm2_t30_150M_UR50D; go to t33_650M only if GPU memory allows). Add a binary classification head.
- Adaptation strategy is a parameter: (a) head-only with the backbone FROZEN, or (b) LoRA/PEFT adapters (frozen backbone). Do NOT full-fine-tune the backbone.

PROTOCOL (obey exactly):
1. Train ONE fine-tuned model PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
2. Train on the TRAIN split ONLY. For early stopping, carve a validation set out of TRAIN using GroupKFold on cluster_id - NEVER use random validation, and NEVER touch cal or test during training. Calibrate on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
3. NEVER re-split randomly and NEVER let a cluster span splits - always use splits.json.
4. Handle class imbalance with weighted cross-entropy (per-class weights). Do NOT use SMOTE or synthetic oversampling.
5. Calibrate by TEMPERATURE SCALING: fit one scalar temperature on the cal-split logits (minimize NLL), apply at inference; optionally add isotonic/Platt on cal if needed.
6. Emit calibrated probabilities and implement a no-call rule: return "no-call" when calibrated p is in ~0.4-0.6, when the genome is out-of-distribution relative to training clusters, or when the target gate fires (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

REGULARIZATION (critical - tiny grouped dataset):
- Use aggressive dropout, early stopping on the GroupKFold-from-train validation set, weight decay, few epochs, small learning rate (~1e-5 to 5e-4).
- Make LoRA rank (4/8/16), learning rate, epochs, and dropout sweepable.

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id) including clusters unseen in training, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic. FOREGROUND the seen-vs-unseen-cluster gap as the overfitting check.
- IMPORTANT: also load reports/metrics_logreg_l2.json (logistic-regression presence/absence baseline) and reports/metrics_esm2_embeddings.json (frozen-embeddings head) if present, and report every metric as a DELTA vs those. Explicitly state that NOT beating the interpretable baseline is a valid, honest result to report.
- This model is NOT interpretable: any attention/saliency attribution is statistical signal, NOT biological causation - state this and defer to the flagged-gene catalog for human-readable evidence.
- Save per-antibiotic metrics to a dict and to JSON (e.g. reports/metrics_esm2_finetune.json). Print a clean summary table (rows = antibiotics, columns = metrics + deltas vs baselines).

Do not fabricate data; load only the files described. Provide the full script.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
