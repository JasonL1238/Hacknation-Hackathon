# Person D — Demo, Responsible-AI & Integration/Glue (Module 03)

> Read [CLAUDE.md](../../CLAUDE.md) and [docs/DATA_SPEC.md](../DATA_SPEC.md) first. Work on
> branch `feat/demo`. **Never blocked** — render the **mock** report object from `_synth.py`
> until Person C delivers real ones (same schema, DATA_SPEC §6). You are also the
> **integration owner**: keep `make all` green as synthetic files are replaced by real.

## You own (edit freely)
- `app/streamlit_app.py`
- `docs/` (MODEL_CARD.md, RESPONSIBLE_AI.md, DECISIONS.md, RISKS.md) — **except**
  `docs/DATA_SPEC.md` (shared seam)
- `Makefile` end-to-end wiring
- optional `src/genome_firewall/llm_summary.py` (flag-gated OpenAI layer)

## Deliverables
1. **Working Streamlit demo** (`streamlit run app/streamlit_app.py`).
2. **Responsible-AI docs** (MODEL_CARD.md, RESPONSIBLE_AI.md) covering each Responsibility
   Requirement from the brief.
3. **Green `make all`** end-to-end.

## Tasks
1. **Report cards** (consume DATA_SPEC §6 objects): per antibiotic show verdict
   (fail/work/no-call, color-coded), **calibrated confidence** bar, **evidence category**
   (i/ii/iii with honest wording — statistical ≠ causal), and **supporting genes/mutations**.
2. **Performance panel** (consume `metrics.json` + PNGs): balanced accuracy, per-class
   recall, F1, AUROC, PR-AUC per drug; **reliability plot**; **no-call rate**;
   **per-genetic-group** generalization.
3. **Mandatory banner** on every result: *"Research prototype — confirm every result with
   standard laboratory testing. Decision support only; a trained professional decides."*
   Plus a **defensive-use statement** and an explicit note that the tool never designs or
   modifies organisms.
4. **Live upload path**: FASTA upload → call Person B's single-genome feature builder →
   Person C's model + report builder → render. Cache models + AMRFinder DB; ship 2–3
   precomputed demo genomes (incl. a known **mecA+ MRSA**) for instant results.
5. **Responsible-AI docs**: write MODEL_CARD.md (species/antibiotics covered & NOT covered,
   metrics, calibration, no-call policy, intended use, limitations) and RESPONSIBLE_AI.md
   mapping each brief requirement (defensive-by-construction, honest generalization,
   calibrated confidence + no-call, honest explanations, human oversight) to how we address
   it on held-out data.
6. **Own the self-questioning cadence**: at each integration wave, run the 7-question
   checklist (see CLAUDE.md) and log answers + evidence in DECISIONS.md; track open items
   in RISKS.md.
7. **Optional OpenAI layer** (off by default, behind a flag): turn the *structured* report
   into a plain-language clinician summary **strictly grounded on the structured evidence**
   — no invented biology, always defers to lab confirmation. Skip if time-poor.

## Definition of done
App renders calibrated per-antibiotic reports with evidence categories + mandatory banner
on both precomputed and uploaded genomes; performance panel shows held-out + per-group
metrics with a reliability plot; `make all` runs clean end-to-end; responsible-AI docs
complete.

## Self-questioning before you call it done
Is the lab-confirmation banner impossible to miss? Does any card imply causation from a
statistical feature? Is the no-call state shown as a legitimate, positive outcome? Does
anything in the UI drift toward organism design?
