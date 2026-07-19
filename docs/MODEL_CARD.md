# Model Card — BioShield AI XGBoost AMR Predictor

## Intended use

Research/demo decision support for predicting existing antibiotic resistance from one
assembled, quality-checked *Staphylococcus aureus* nucleotide FASTA. The app is not a
diagnostic or treatment system. Every output requires confirmation with standard
laboratory antimicrobial-susceptibility testing.

## Production model

- Model version: `bioshield-xgboost-v1`.
- Input: 144 binary AMRFinderPlus gene/mutation features.
- Learner: one XGBoost classifier per antibiotic.
- Calibration: sigmoid map fitted to Mash-clustered out-of-fold XGBoost probabilities.
- Final fit: all labeled genomes for the antibiotic, with each strict duplicate family
  contributing approximately one total vote through inverse-family sample weights.
- Decision rule: `P(R) >= 0.5`; probabilities from 0.40 through 0.60 are no-call.
- Artifacts and reproducibility manifest: `data/processed/final_models/`.

The final all-data fit has no internal test set. Its manifest diagnostics are training
OOF diagnostics, not independent final performance estimates.

## Coverage

- Species: *Staphylococcus aureus* only.
- Antibiotics: cefoxitin, ciprofloxacin, clindamycin, erythromycin, gentamicin, and
  tetracycline.
- Labeled rows by drug: 1,811; 2,328; 1,306; 2,041; 2,065; and 2,060 respectively.
- Not covered: other organisms, raw FASTQ reads, read assembly, species identification,
  antibiotics outside this list, or novel mechanisms absent from AMRFinderPlus.

## Data and duplicate control

Features and AST labels originate from the repository's BV-BRC/NCBI pipeline. The frozen
whole-genome audit contains 2,542 genomes, 1,460 strict Mash duplicate groups, and 136
broader genetic clusters. No rows are deleted. Grouped folds keep each broader cluster
intact, and supervised fitting weights a labeled member by `1 / duplicate-family size`.

Inference is locked to AMRFinderPlus 4.2.7 database `2026-05-15.1`. The app refuses to
predict if the runtime database differs from the frozen feature contract.

## Historical grouped-test evidence

Before the all-data refit, XGBoost was evaluated on the existing Mash-separated test
partition. Macro results across six drugs were: balanced accuracy 0.8475, recall-R 0.7980,
recall-S 0.8971, F1 0.7893, AUROC 0.9216, PR-AUC 0.8531, Brier 0.1113, no-call rate 0.0361,
and accuracy on called samples 0.8883. Full per-drug and per-cluster results are retained
in `reports/soft_ensemble/`.

Important caveat: XGBoost was chosen for deployment after these reports had been
inspected. They are useful historical evidence but are not an unbiased final estimate for
the selected production model. A fresh external dataset is required before making a final
generalization claim.

## Outputs and explanations

For each antibiotic, the app shows calibrated `P(resistant)`, likely-to-fail /
likely-to-work / no-call, class confidence, relevant catalog markers, and clearly labeled
statistical evidence when available. It also displays every AMR symbol detected by
AMRFinderPlus, including symbols outside the frozen model schema; out-of-schema symbols
are not silently used as model inputs.

## Privacy and deployment

The authenticated Streamlit research app processes one FASTA synchronously. Upload bytes,
the temporary FASTA, and the AMRFinder TSV are removed immediately after success or
failure. The genome is not uploaded to Supabase Storage. Free demo hosting is not suitable
for protected health information, clinical reliability, or regulated use.

## Limitations

- Historical and potentially geographically biased training data.
- Weak performance can occur on unseen genetic lineages; tetracycline was especially
  difficult in the historical held-out partition.
- Catalog-based features cannot represent genuinely novel resistance mechanisms.
- The target-gate layer cannot directly verify essential genes that AMRFinderPlus does not
  emit as AMR features; those assumptions are documented in `docs/DECISIONS.md`.
- XGBoost feature influence is statistical association, not biological causation.
- Not cleared or approved as a clinical diagnostic device.
