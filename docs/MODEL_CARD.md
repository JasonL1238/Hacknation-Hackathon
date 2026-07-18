# Model Card — Genome Firewall (S. aureus AMR predictor)

_Fill in as results land._

## Intended use
Defensive decision support: predict/explain existing antibiotic resistance from a
reconstructed *S. aureus* genome. **Not** a treatment decision-maker. Every result must be
confirmed by standard laboratory testing.

## Coverage
- **Species covered:** Staphylococcus aureus only.
- **Antibiotics covered:** _(list, once chosen)_
- **NOT covered:** other species; antibiotics not listed; sample-to-genome steps.

## Data
- Source: BV-BRC, lab-measured AST only. Genome count / label counts: _(fill)_
- Split: grouped by genetic cluster (Mash/skani), whole clusters per split, unseen groups
  held out. De-dup collapsed _(N)_ near-identical genomes.

## Performance (held-out grouped-test split)
_(balanced accuracy, recall_R, recall_S, F1, AUROC, PR-AUC per drug, Brier, no-call rate,
accuracy-on-called, per-genetic-group breakdown, baseline vs ESM-2 deltas)_

## Calibration
_(reliability diagram, Brier; calibration method: isotonic/Platt on cal split)_

## No-call policy
Returns no-call for ambiguous probability, out-of-distribution genomes, or target-gate
firing. No-call rate: _(fill)_.

## Explanations
Evidence categories: (i) known resistance gene/mutation, (ii) statistical-only association
(**not** proven causal), (iii) no known signal.

## Limitations
Research prototype; historical data; not approved for clinical use.
