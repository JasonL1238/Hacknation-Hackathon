# Responsible AI — how we address each Responsibility Requirement

_Map each brief requirement to concrete evidence in our system._

| Requirement (from brief) | How we address it | Evidence / where to see it |
|---|---|---|
| **Defensive by construction** | Only predicts/explains existing resistance; never designs or modifies organisms; explicit refusal in UI + code | CLAUDE.md scope rule; UI defensive statement |
| **Honest generalization** | Grouped split by genetic similarity; metrics on unseen groups reported | `metrics.json` per-group; MODEL_CARD |
| **Calibrated confidence + no-call** | Isotonic calibration on held-out cal split; reliability plot + Brier; no-call for weak/OOD/conflicting evidence | reliability PNG; no-call rate in app |
| **Honest explanations** | Evidence categories separate known catalog hits (i) from statistical-only (ii); SHAP never shown as causal | report cards; report.py |
| **Human oversight** | Mandatory "confirm with standard lab testing" banner on every result; decision-support framing | Streamlit banner on every card |

## Coverage statement (state plainly in the demo)
Covers: *S. aureus* + the listed antibiotics. Does NOT cover: other species, other drugs,
or any sample-to-genome processing.
