# ESM-2 Protein Embeddings + Linear/GBM Head

> **One-liner:** Embed each genome's AMRFinderPlus-flagged protein sequences with a frozen ESM-2 protein language model, mean-pool to one vector per genome, and train a simple logistic-regression or gradient-boosting head on the same grouped splits.
> **Category:** sequence-DL ·
> **Runs on:** Colab GPU (embed) → Colab/local CPU (head) ·
> **Priority:** recommended ·
> **Interpretable:** no (head partially)

## Why it fits Genome Firewall
The presence/absence baseline can only see genes AMRFinderPlus already has in its catalog: a resistance protein that carries a novel or divergent mutation the catalog does not flag becomes an all-zeros row and is silently missed. A frozen protein language model reads the actual amino-acid sequence of each flagged protein, so a mutated `mecA`, `gyrA`, or `pbp` variant lands in a nearby-but-distinct region of embedding space and can still push the R/S probability. That sequence-level generalization beyond binary presence/absence is the genuine value proposition here — not a leaderboard bump on catalog-covered drugs, where the linear baseline is already near-optimal. Because embeddings are computed once and cached, the actual classifier is still a tiny head trained on a few hundred genomes, so it re-fits cheaply per grouped split and stays compatible with the same calibration step as every other model.

## When to prefer it / when to skip it
Prefer this over the pure presence/absence baseline specifically when you want to catch resistance from *mutated gene variants* that the catalog misses — that is the one thing a sequence model can do that the baseline structurally cannot. Skip it (or keep it as an analysis, not the production model) if it does not beat the logistic-regression baseline on held-out grouped-test Brier and balanced accuracy: **not beating the interpretable baseline is a valid, honest, reportable result**, and you should report it as such rather than tuning until the numbers look good. Choose this frozen-embeddings route over full fine-tuning (file 18) first — it is far cheaper, far less prone to overfitting on a few hundred genomes, and lets you sweep the head locally in seconds.

## Data interface (the contract this code must respect)
- Protein inputs are the prepared per-genome FASTAs under `data/interim/esm2_proteins/<genome_id>.faa`; the same directory also contains `all_amr_proteins.faa` and `manifest.csv`. Create or refresh them locally with `python scripts/prepare_esm2_fastas.py`.
- On the GPU runtime: read those prepared AMRFinderPlus AMR-hit protein sequences, embed each protein with ESM-2, and **mean-pool** across proteins (and residues) to one fixed-length vector per `genome_id`. Save the per-genome embedding matrix (index = `genome_id`) to disk and download it.
- Locally: read the cached embeddings as X, aligned to `genome_id`. Optionally read `data/processed/features.parquet` to **concatenate** the binary presence/absence columns with the embedding, and test concatenate-vs-replace.
- Read `data/processed/labels.csv`, filter to one antibiotic at a time, map `label` R→1, S→0.
- Read `data/processed/splits.json` for the grouped train/cal/test assignment and `cluster_id`; never re-split randomly. Fit the head on **train** only, calibrate on **cal** only, report metrics on **test** only.
- Read `db/drugs_saureus.csv` so the downstream target gate can still veto a "likely-to-work" call when the drug's molecular target is absent.

### Concrete local and Colab paths
- This machine's repository root is `/Users/jasonli/Documents/GitHub/Hacknation-Hackathon`.
- A Colab runtime cannot read that Mac path. Clone the tracked repository to `/content/Hacknation-Hackathon`, mount Google Drive, and copy the locally generated `data/interim/esm2_proteins/` directory to `/content/drive/MyDrive/Hacknation-Hackathon-sequence-data/data/interim/esm2_proteins/`.
- Generated notebook code must define `REPO_ROOT` and `SEQUENCE_ROOT` separately, allow both to be overridden by environment variables, validate every required path before training, and join records by the `genome_id` prefix before the first `|` in each protein FASTA record ID.
- **Relative-path option:** when running locally from the repository root, `data/interim/esm2_proteins/`, `data/processed/`, and `db/` are valid relative paths. In Colab, relative paths work only after the protein directory has actually been copied into `/content/Hacknation-Hackathon/data/interim/esm2_proteins/`; cloning alone does not provide it because `data/interim/*` is ignored by Git. The notebook must `%cd /content/Hacknation-Hackathon` (or use `os.chdir`) and verify the files before using relative paths.

## Adversarial checks it must survive
- **No leakage (Rule 1):** The GPU embedding step is per-genome and label-free, so it cannot leak labels — but the *head* must still be fit on train only, calibrated on cal only, and any head hyperparameter search must use GroupKFold on `cluster_id` inside train. Confirm no `cluster_id` spans splits before fitting.
- **Clonal memorization:** ESM-2 embeddings of proteins from a single clonal lineage cluster tightly, so the head can learn the lineage instead of the mechanism and look great on seen clusters while collapsing on unseen ones. Mitigate by reporting per-genetic-group metrics including unseen clusters, and by comparing the unseen-cluster drop against the baseline's drop — a bigger drop means more memorization.
- **Calibration (Rule 2):** High-dimensional embeddings feeding even a simple head can produce over-confident probabilities; calibrate on `cal` and report reliability + Brier on `test`, never on train.
- **Honest explanations (Rule 5):** The head is only *partially* interpretable — a large weight on an embedding dimension is an opaque statistical association, not a named gene and definitely not biological causation. Attribute calls back to the specific flagged proteins that produced the embedding, and label everything as statistical-only signal.
- **Honest comparison protocol:** Run the SAME grouped splits and the SAME calibration protocol as the baseline and report deltas (balanced accuracy, PR-AUC, Brier) vs the logistic-regression presence/absence baseline. Do not report absolute numbers in isolation.
- **No forced calls (Rule 3):** Feed calibrated probabilities into the no-call band rather than thresholding at 0.5.

## Hyperparameters worth sweeping
- **ESM-2 model size:** `facebook/esm2_t12_35M_UR50D` (fast, cheap) → `esm2_t30_150M_UR50D` → up to `esm2_t33_650M_UR50D`. Bigger is not automatically better on a few hundred genomes; sweep and report.
- **Pooling variant:** mean / max / attention pooling across proteins and residues (mean is the sane default).
- **Feature composition:** embeddings-only vs `concat(embeddings, presence/absence)` vs presence/absence-only — test all three; concat is the most likely to actually add value.
- **Head choice:** logistic regression (sweep `C` over `np.logspace(-3, 2, 12)`, `class_weight="balanced"`) or gradient boosting (LightGBM/XGBoost — `n_estimators`, `max_depth` 2–4, `learning_rate` 0.01–0.1, `scale_pos_weight` for imbalance).
- Optional dimensionality reduction (PCA to tens of components) before the head, to fight overfitting on a small dataset.
- Cache embeddings to disk so all head/pooling/composition sweeps are cheap and never re-run the GPU step.

## Calibration & no-call handling
Calibrate the head exactly like every other model: `CalibratedClassifierCV(cv="prefit")` (or an isotonic/Platt map) fit on the **cal** split; prefer isotonic if cal is large enough, else sigmoid/Platt. The calibrated probability drives the no-call logic: return `no-call` when calibrated p sits in the ambiguous band (~0.4–0.6), when the genome is out-of-distribution (embedding far from all training clusters — you can reuse embedding distance as an OOD signal here), or when the target gate fires (drug target gene absent → do not claim "likely to work" from marker absence alone).

## Metrics to report
On the held-out grouped **test** split, and broken down **per genetic group** (including groups unseen in training): balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, **Brier score**, **reliability diagram**, and no-call rate + accuracy-on-called. Report every number as a **delta vs the logistic-regression presence/absence baseline**, and call out specifically any case where this model recovers a resistant genome the baseline missed because of a catalog-uncovered mutation.

## Copy-paste LLM prompt
Paste the block below into ChatGPT/Claude to get complete, runnable training + testing code for this model.

```text
I am building "Genome Firewall", a strictly DEFENSIVE research prototype that predicts, per antibiotic, whether a reconstructed Staphylococcus aureus genome is likely-to-fail (Resistant) or likely-to-work (Susceptible) treatment, with a CALIBRATED confidence. It only predicts resistance that already exists; it never designs or modifies organisms. The judged priority is ML RIGOR AND CALIBRATION (Brier score + reliability diagram on a held-out grouped-test split) over raw accuracy.

I want to use ESM-2 PROTEIN EMBEDDINGS with a simple LINEAR or GRADIENT-BOOSTING head. This runs in TWO stages in GOOGLE COLAB: (1) a GPU stage that computes frozen ESM-2 embeddings, and (2) a CPU stage in the same notebook that trains and calibrates the head. Write complete, runnable Colab notebook cells for BOTH stages, including Google Drive mounting and path validation.

DATA CONTRACT (files already exist on disk):
- PATHS: on this Mac, `REPO_ROOT=/Users/jasonli/Documents/GitHub/Hacknation-Hackathon` and `SEQUENCE_ROOT=REPO_ROOT`. In Colab, use `REPO_ROOT=/content/Hacknation-Hackathon` for the Git clone and `SEQUENCE_ROOT=/content/drive/MyDrive/Hacknation-Hackathon-sequence-data` for the large untracked data copied from this Mac. At the top of the notebook, mount Google Drive when running in Colab, define both roots as `pathlib.Path` values (environment-variable overrides `GENOME_FIREWALL_ROOT` and `GENOME_FIREWALL_SEQUENCE_ROOT`), and fail with a clear missing-path error rather than silently using fabricated data.
- RELATIVE PATHS: if all required folders have been copied beneath the repository, first change the working directory to REPO_ROOT and use `data/interim/esm2_proteins`, `data/processed`, and `db` as relative paths. In Colab, cloning does not include `data/interim/esm2_proteins`; confirm that directory exists and contains `.faa` files before training. Do not assume a relative path exists merely because the repository was cloned.
- data/processed/features.parquet: one row per genome, index = genome_id (str). Columns are binary int8 presence/absence of AMR gene symbols (e.g. mecA, blaZ, ermC, tetK, aac(6')-aph(2'')) and named point mutations (e.g. gyrA_S84L, grlA_S80F). Column set is the union across the dataset; absent = 0; no missing values. Tens-to-low-hundreds of sparse binary columns, hundreds-to-low-thousands of genomes.
- data/processed/labels.csv: columns genome_id, antibiotic, label in {R,S} (R = resistant/likely-to-fail, S = susceptible/likely-to-work), source, method. One row per (genome_id, antibiotic). About 4-6 antibiotics (e.g. erythromycin, clindamycin, ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin). Classes are imbalanced.
- data/processed/splits.json: maps genome_id -> {"split": "train"|"cal"|"test", "cluster_id": int}. This is a GROUPED split: every genome in a cluster_id is in exactly ONE split; no cluster spans splits. Some clusters are unseen in training.
- db/drugs_saureus.csv: columns antibiotic, drug_class, target_genes (;-sep), known_markers (;-sep), standardized_name. Used for a deterministic target gate.
- SEQUENCE_ROOT/data/interim/esm2_proteins/<genome_id>.faa: one prepared FASTA per genome containing translated AMRFinderPlus rows with Type == AMR. Record IDs begin `<genome_id>|`. The directory also contains `all_amr_proteins.faa` and `manifest.csv` with columns genome_id, protein_count, fasta_file. These are generated locally by `python scripts/prepare_esm2_fastas.py`. If a genome has no flagged AMR proteins, produce a zero vector for it. Do not feed the nucleotide `.fna` files directly to ESM-2.

STAGE 1 (COLAB GPU) - compute embeddings:
- Use the Hugging Face transformers ESM-2 checkpoints. Make the checkpoint a parameter and support facebook/esm2_t12_35M_UR50D, facebook/esm2_t30_150M_UR50D, and facebook/esm2_t33_650M_UR50D.
- For each genome, embed each flagged protein and MEAN-POOL across residues (mask padding) to get a per-protein vector, then MEAN-POOL across the genome's proteins to get ONE fixed-length vector per genome_id. Also implement max-pooling and attention-pooling as switchable options.
- Batch on GPU (cuda), use no_grad (frozen backbone, no fine-tuning), and handle long sequences by truncating to the model max length. This is the only GPU-heavy step.
- Save the result as a DataFrame indexed by genome_id (embedding columns emb_0..emb_d) to parquet so it can be downloaded and reused. Cache so re-runs are cheap.

STAGE 2 (LOCAL CPU) - head + calibration + evaluation:
1. Load the cached per-genome embeddings, labels.csv, splits.json, drugs_saureus.csv. Support three feature compositions: embeddings only, presence/absence only, and concat(embeddings, presence/absence) - make it a parameter and run all three.
2. Train ONE head PER antibiotic (loop over antibiotics in labels.csv). Map label R->1, S->0.
3. Fit the head on the TRAIN split ONLY. Fit probability calibration on the CAL split ONLY. Report ALL metrics on the TEST split ONLY.
4. NEVER re-split randomly and NEVER let a cluster span splits - always use splits.json. If you need internal validation for head hyperparameters, use GroupKFold on cluster_id WITHIN the train split only; never touch cal or test.
5. Handle class imbalance with class_weight="balanced" (logistic) or scale_pos_weight (gradient boosting). Do NOT use SMOTE or synthetic oversampling.
6. Head options: sklearn LogisticRegression (sweep C over np.logspace(-3,2,12)) OR LightGBM/XGBoost (n_estimators, max_depth 2-4, learning_rate 0.01-0.1). Optionally PCA the embeddings to tens of components first to reduce overfitting. Make head choice a parameter.
7. Calibrate the fitted head with CalibratedClassifierCV(cv="prefit") on the cal split (try isotonic and sigmoid; pick per antibiotic by cal-split Brier).
8. Emit calibrated probabilities and implement a no-call rule: return "no-call" when calibrated p is in ~0.4-0.6, when the genome's embedding is far from all training-cluster embeddings (OOD), or when the target gate fires (if the drug's target_genes are all absent, do not output "likely to work" from marker absence alone).

OUTPUT / METRICS:
- On the TEST split, and additionally broken down PER genetic group (cluster_id) including clusters unseen in training, compute: balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC, Brier score, and no-call rate + accuracy-on-called. Plot a reliability diagram per antibiotic.
- IMPORTANT: also load reports/metrics_logreg_l2.json if present (the logistic-regression presence/absence baseline) and report every metric as a DELTA vs that baseline. Explicitly note that failing to beat the baseline is a valid, honest result to report. Flag any resistant test genome this model calls correctly that the baseline missed.
- The head is only PARTIALLY interpretable: a big embedding-dimension weight is an opaque statistical association, NOT a named gene and NOT biological causation. State this in the output.
- Save per-antibiotic metrics (and per-composition) to a dict and to JSON (e.g. reports/metrics_esm2_embeddings.json). Print a clean summary table (rows = antibiotics, columns = metrics + deltas vs baseline).

Do not fabricate data; load only the files described. Provide the full script for both stages.
```

> _Research prototype — confirm every result with standard laboratory testing; a trained professional makes the decision._
