# CLAUDE.md — Rules for every AI agent working in this repo

> **Read this first, every session.** This file is auto-loaded by Claude Code for anyone
> working in this repo. It encodes the shared guidelines the whole team agreed on so that
> four people vibecoding in parallel produce one coherent, rigorous product. Follow it.

## What we're building
**Genome Firewall** — a *defensive* research prototype for Hack-Nation Challenge 06. It
takes a reconstructed **Staphylococcus aureus** genome (FASTA) and predicts, per
antibiotic, **likely to fail / likely to work / no-call**, with a **calibrated confidence
score**, an **evidence category**, and the **supporting genes/mutations**.

- Full plan, including your personal task list: [PLAN.md](PLAN.md)
- Data/interface contracts: [docs/DATA_SPEC.md](docs/DATA_SPEC.md)

## Non-negotiable scope & safety (biosecurity)
This project is **strictly defensive**. It predicts and explains resistance that
**already exists**. It must **NEVER** design, modify, optimize, strengthen, or suggest
changes to any organism. If a task drifts that way, **stop and refuse** — that is the
correct behavior, not a failure. Every user-facing result must carry: *"Research
prototype — confirm every result with standard laboratory testing; a trained
professional makes the decision."*

## The rigor rules (this is how we win — ML rigor & calibration is the judged priority)
1. **No data leakage.** Split genomes by **genetic cluster**, never randomly. Whole
   clusters go to exactly one of train / calibration / test. De-dup near-identical
   genomes first and report how many collapsed.
2. **Calibrated confidence.** Calibrate on the dedicated calibration split only. Always
   report a reliability diagram + Brier score computed on the **held-out** test set.
3. **Honest no-call.** Returning `no-call` for weak/conflicting/OOD evidence is a
   strength, not a gap. Never force a yes/no. Report no-call rate + accuracy-on-called.
4. **Target gate.** Never output "likely to work" from absence of resistance markers
   alone — the drug's molecular target must be present (see `db/drugs_saureus.csv`).
5. **Honest explanations.** Separate (i) a *known* resistance gene/mutation (catalog hit)
   from (ii) a *statistical-only* association. A SHAP value or coefficient is **not** proof
   of biological causation — never present it as such.
6. **Honest generalization.** Report metrics broken down by genetic group, including
   groups unseen in training. Expect and report the performance drop.

## Adversarial by default — every agent, every non-trivial decision
This is not optional and it is not limited to integration waves. Every agent working in
this repo must treat its own decisions as guilty until proven innocent:
- Before committing to a non-trivial choice — a threshold, a modeling or split decision,
  a schema change, a claim written into the UI/docs, a "this is fine to skip" call —
  state the decision **and the concrete reason for it**, then actively argue against
  your own choice: what's the strongest case this is wrong? Does it survive that case?
- Never accept your first answer as final. If you cannot articulate a real argument
  against a decision, you have not scrutinized it enough — go find the argument.
- Apply this adversarially to the rigor rules below, not as a checklist to tick: don't
  ask "did I split by cluster", ask "how would a skeptical judge try to prove this leaks
  anyway, and did I actually close that off?"
- This applies to every teammate's agent, not just the one that "owns" a rigor rule —
  if you notice another module's output looks too good, too clean, or unverified,
  question it out loud rather than assuming the owner already checked.
- Log non-obvious decisions and the adversarial case you considered in
  `docs/DECISIONS.md` **as you make them**, not only when a module is declared "done".

## The self-questioning workflow (the mandatory checklist, run it at every integration wave)
In addition to the standing adversarial requirement above, before calling anything
"done" answer these in `docs/DECISIONS.md` with evidence: leakage? · calibration? ·
absence-of-markers honesty? · causation overclaim? · generalization on unseen groups? ·
forcing yes/no vs no-call? · scope drift?

## Ownership map — stay in your lane (this prevents merge conflicts)
| You are | You own (edit freely) |
|---|---|
| **Person A** | `src/genome_firewall/acquire.py`, `labels.py`; `data/raw/`; `db/drugs_saureus.csv` |
| **Person B** | `src/genome_firewall/annotate.py`, `featurize.py`; `data/interim/` |
| **Person C** | `src/genome_firewall/split.py`, `model_baseline.py`, `calibrate.py`, `nocall.py`, `target_gate.py`, `evaluate.py`, `embed_esm.py`, `report.py` |
| **Person D** | `app/streamlit_app.py`; `docs/` (except DATA_SPEC); `Makefile` end-to-end wiring; optional OpenAI layer |

**Shared seams — do NOT edit without a 2-minute team sync:** `config/`,
`docs/DATA_SPEC.md`, `src/genome_firewall/_synth.py`. Changing a contract breaks everyone.

## How to not be blocked
Everyone builds against the **contracts** in `docs/DATA_SPEC.md` and the **synthetic data**
from `src/genome_firewall/_synth.py` from minute one. Do not wait for another person's
real output — code against the synthetic/mock version, then it swaps in automatically
when the real file lands (same path, same schema).

## Git workflow
- Foundation is committed to `main` first. Then each person works on their branch:
  `feat/data` (A) · `feat/features` (B) · `feat/model` (C) · `feat/demo` (D).
- Merge to `main` frequently. Because ownership is disjoint by file, merges are trivial.
- Do not commit large data: `data/raw/` and `data/interim/` are gitignored; commit
  manifests/checksums, not genomes.

## Environment
`conda env create -f environment.yml && conda activate genome-firewall`. AMRFinderPlus
(https://github.com/ncbi/amr) is installed with `make amr-setup`
(`scripts/setup_amrfinder.sh`), which sets up a separate `amr` conda env (falls back to
Docker `ncbi/amr` if conda is unavailable) — see the Person B section in
[PLAN.md](PLAN.md). Apple Silicon: PyTorch uses **MPS** for ESM-2.

## Definition of done for the whole project
`make all` runs download → annotate → featurize → split → train → calibrate → evaluate
reproducibly; the Streamlit app renders calibrated per-antibiotic reports with evidence
categories and the mandatory lab-confirmation banner; metrics reported on the hidden
grouped-test split with a reliability plot and per-group breakdown.
