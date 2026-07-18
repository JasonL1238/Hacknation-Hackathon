# DECISIONS.md — decisions + self-questioning log

Every integration wave, run the 7-question checklist (CLAUDE.md) and log answers +
evidence here. Also record every non-obvious modeling/data choice with its rationale.

## Template
```
### <date/wave> — <decision or question>
- What: ...
- Why: ...
- Evidence: ... (numbers, plots, asserts)
- Owner: Person X
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
- [ ] Antibiotic choice + label counts (Person A).
- [ ] Split thresholds justified (Person C).
