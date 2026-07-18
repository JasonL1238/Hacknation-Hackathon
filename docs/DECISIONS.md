# DECISIONS.md — decisions + self-questioning log

At every milestone, run the 7-question checklist (CLAUDE.md) and log answers + evidence
here. Also record every non-obvious modeling/data choice with its rationale, as you make
it — per CLAUDE.md's adversarial-by-default rule, include the strongest case against the
decision and why it doesn't hold.

## Template
```
### <date> — <decision or question>
- What: ...
- Why: ...
- Adversarial case considered: ... (the strongest argument this is wrong)
- Evidence: ... (numbers, plots, asserts)
```

## Log
_(empty — fill as you go)_

### Open questions to answer before "done"
- [ ] Leakage: proof no cluster spans train/test (assert output + de-dup count).
- [ ] Calibration: reliability plot on held-out tracks the diagonal; Brier reported.
- [ ] Honesty: no "likely to work" from marker-absence without target present.
- [ ] Causation: no SHAP/coefficient presented as biological cause.
- [ ] Generalization: metrics on unseen genetic groups reported (with the drop).
- [ ] Uncertainty: no-call rate + accuracy-on-called reported per drug.
- [ ] Scope: nothing drifts toward organism design.
- [ ] Antibiotic choice + label counts justified.
- [ ] Split thresholds justified.
