# Model & Method Catalog — Genome Firewall

This folder is the **menu of models and methods worth testing** for the per-antibiotic
R/S prediction task. Each file is a self-contained plan for one model: why it fits this
data, how to run it under our rigor rules, and — most importantly — a **copy-paste LLM
prompt** you can drop into ChatGPT/Claude to get complete, runnable train+test code for
that model without any repo context.

> Read [../CLAUDE.md](../CLAUDE.md) and [../docs/DATA_SPEC.md](../docs/DATA_SPEC.md) for
> the binding rules and schemas. These files are **plans, not results** — no numbers here
> are real until you run them.

---

## The one thing to remember

**The judged priority is ML rigor & calibration, not raw accuracy.** Every model here is
scored the same way: fit on `train`, calibrate on `cal`, and report **Brier score +
reliability diagram on the held-out grouped `test` split**, broken down per genetic group
(including clusters unseen in training). A slightly-less-accurate model that is honestly
calibrated, interpretable, and knows when to `no-call` **beats** a flashier one that is
overconfident or leaky. Judge the bakeoff on Brier and per-group generalization first,
aggregate accuracy second.

**The baseline to beat is [01_logistic_regression_l2.md](01_logistic_regression_l2.md).**
Report every other model's deltas relative to it. Because AMRFinderPlus already flags the
catalogued causal genes, the presence/absence matrix hands logistic regression most of
the signal — so a complex model that *crushes* the baseline is a **red flag to
investigate** (clonal memorization), not an automatic win.

---

## The shared data contract (every file's code consumes this)

- `data/processed/features.parquet` — one row per genome, index `genome_id`; binary int8
  presence/absence of AMR genes + named point mutations. Sparse; ~tens–hundreds of cols.
- `data/processed/labels.csv` — `genome_id, antibiotic, label∈{R,S}, source, method`.
- `data/processed/splits.json` — `genome_id → {split: train|cal|test, cluster_id}`.
  **Grouped:** whole clusters go to one split; no cluster spans splits.
- `db/drugs_saureus.csv` — drug → class, target genes, known markers (feeds the target gate).

**Protocol for all:** one model per antibiotic · fit on `train` · calibrate on `cal` ·
evaluate on `test` · never re-split randomly · any internal val set is carved from
`train` via GroupKFold on `cluster_id`.

---

## The full catalog

| # | Model / method | Category | Runs on | Priority | Interpretable |
|---|---|---|---|---|---|
| 01 | [Logistic Regression (L2)](01_logistic_regression_l2.md) | linear | local CPU | **core** | yes |
| 02 | [Logistic Regression (L1 / Elastic-net)](02_logistic_regression_l1_elasticnet.md) | linear | local CPU | recommended | yes |
| 03 | [Bernoulli Naive Bayes](03_bernoulli_naive_bayes.md) | probabilistic | local CPU | recommended | partial |
| 04 | [Linear SVM](04_linear_svm.md) | linear | local CPU | recommended | partial |
| 05 | [RBF SVM](05_rbf_svm.md) | kernel | local CPU | stretch | no |
| 06 | [Random Forest](06_random_forest.md) | tree-ensemble | local CPU | recommended | partial |
| 07 | [Extra Trees](07_extra_trees.md) | tree-ensemble | local CPU | stretch | partial |
| 08 | [HistGradientBoosting](08_hist_gradient_boosting.md) | tree-ensemble | local CPU | recommended | partial |
| 09 | [XGBoost](09_xgboost.md) | tree-ensemble | local CPU (+GPU) | recommended | partial |
| 10 | [LightGBM](10_lightgbm.md) | tree-ensemble | local CPU (+GPU) | recommended | partial |
| 11 | [CatBoost](11_catboost.md) | tree-ensemble | local CPU (+GPU) | recommended | partial |
| 12 | [k-Nearest Neighbors](12_knn.md) | instance-based | local CPU | stretch (control) | partial |
| 13 | [TabPFN](13_tabpfn.md) | tabular-DL | local CPU/GPU | recommended | no |
| 14 | [MLP (tabular)](14_mlp_tabular.md) | tabular-DL | local CPU/GPU | stretch | no |
| 15 | [TabNet](15_tabnet.md) | tabular-DL | local CPU/GPU | stretch | partial |
| 16 | [FT-Transformer](16_ft_transformer.md) | tabular-DL | Kaggle GPU | stretch | no |
| 17 | [ESM-2 embeddings + head](17_esm2_embeddings_linear.md) | sequence-DL (protein) | Kaggle GPU → local | recommended | no |
| 18 | [ESM-2 fine-tune](18_esm2_finetune.md) | sequence-DL (protein) | Kaggle GPU | stretch | no |
| 19 | [Nucleotide Transformer](19_nucleotide_transformer.md) | sequence-DL (DNA) | Kaggle GPU | stretch | no |
| 20 | [Calibration methods](20_calibration_methods.md) | method | local CPU | **core** | n/a |
| 21 | [Conformal prediction](21_conformal_prediction.md) | method | local CPU | recommended | partial |
| 22 | [Stacking / voting ensemble](22_stacking_ensemble.md) | method | local CPU | stretch | no |
| 23 | [DNABERT-2](23_dnabert2.md) | sequence-DL (DNA) | Kaggle GPU → local | stretch | no |
| 24 | [HyenaDNA](24_hyenadna.md) | sequence-DL (DNA) | Kaggle GPU → local | stretch | no |

---

## Suggested order (local first, Kaggle for the heavy DL)

**Tier 1 — do these first (local CPU, minutes).** They are cheap, calibratable, and set
your honest bar: 01 (L2 LR baseline), 20 (calibration — applies to *everything*), 03
(Bernoulli NB — purpose-built for binary features), 08 (HistGradientBoosting), 13
(TabPFN — often the best calibration for near-zero effort). Add 21 (conformal) early
since it gives you principled `no-call` on top of any of them.

**Tier 2 — round out the local sweep.** 02 (L1/elastic-net for feature selection), 04
(linear SVM), 06 (random forest), 09/10/11 (XGBoost/LightGBM/CatBoost). Include 12 (kNN)
purely as a **clonality control** — it tells you how much "accuracy" is just lineage
matching. 05 (RBF SVM), 07 (extra trees), 14 (MLP) if time allows.

**Tier 3 — Kaggle GPU (the DL track).** Two families here, both following the same
embed-then-head protocol:
- **Protein (ESM-2):** 17 (frozen embeddings + head) is the main planned stretch — embed
  on GPU, download vectors, sweep cheap heads locally; then 18 (ESM-2 fine-tune).
- **DNA (nucleotide LMs):** 23 (DNABERT-2, multi-species — best domain fit), 24 (HyenaDNA,
  single-nucleotide + long context but human-pretrained → domain-shift caveat), and 19
  (Nucleotide Transformer). Plus 16 (FT-Transformer) as a tabular-transformer test.

The genuine value story for sequence models is catching resistance from a *mutated* gene
variant the AMRFinder catalog misses — DNA models (23/24) additionally reach non-coding /
regulatory and single-nucleotide signal that protein models and the presence/absence
matrix can't express. Target that, and report deltas vs the baseline honestly (no gain is
a valid result).

**Tier 4 — combine.** 22 (stacking/voting) over the best base models, with out-of-fold
meta-features built via GroupKFold on `train` only. Keep the LR baseline as the
explainable model even if the stack scores higher.

---

## Local vs Kaggle — the practical split

- **Local (CPU):** everything in Tiers 1–2, plus the classifier *heads* for the DL track.
  These run in seconds-to-minutes per antibiotic — mass-test them all.
- **Kaggle (GPU):** only the embedding / fine-tuning compute (17–19) and the data-hungry
  tabular transformers (16). Key efficiency trick from [17](17_esm2_embeddings_linear.md):
  the GPU step is *only* producing embeddings — **compute + cache embeddings on Kaggle,
  download the per-genome vectors, then sweep heads + calibration locally** on the same
  grouped splits.

---

## How to use a model file

1. Open the file, skim **Why it fits** and **Adversarial checks** so you know its traps.
2. Copy the **Copy-paste LLM prompt** block into ChatGPT/Claude — it is self-contained
   (embeds the full data contract + protocol), so you get correct, leak-free code back.
3. Run it against the real `data/processed/` artifacts. Record results + the adversarial
   answers in [../docs/DECISIONS.md](../docs/DECISIONS.md).

> _Research prototype — confirm every result with standard laboratory testing; a trained
> professional makes the decision._
