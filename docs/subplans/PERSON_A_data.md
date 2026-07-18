# Person A — Data, Labels & Drug Database

> Read [CLAUDE.md](../../CLAUDE.md) and [docs/DATA_SPEC.md](../DATA_SPEC.md) first. Work on
> branch `feat/data`. You are **fully independent from t=0** — nobody blocks you and you
> block Person C's *real* run (they use synthetic labels until you deliver).

## You own (edit freely)
- `src/genome_firewall/acquire.py`
- `src/genome_firewall/labels.py`
- `data/raw/` (gitignored — commit the manifest, not the genomes)
- `db/drugs_saureus.csv`

## Deliverables (the contracts you produce)
1. **`data/processed/labels.csv`** — schema in DATA_SPEC §3. Lab-measured AST only.
2. **Quality-filtered genome FASTAs** in `data/raw/` + a `data/raw/manifest.csv`
   (genome_id, accession, source, checksum, quality flags).
3. **`db/drugs_saureus.csv`** — schema in DATA_SPEC §5.

## Tasks
1. **Pull from BV-BRC** (`https://www.bv-brc.org/api/`, via `requests` RQL; `p3-*` CLI as
   fallback):
   - `genome_amr` filtered to *Staphylococcus aureus*, keep rows with a **measured**
     `laboratory_typing_method` (MIC/disk) and a real `resistant_phenotype`.
   - **Exclude model-predicted phenotype fields** (challenge rule — critical).
   - Join to `genome` on `genome_id`; keep good-quality genomes (genome_status /
     genome_quality / contig count). Download contigs (FASTA).
2. **Pick the antibiotics** — rank by count of clean R/S labels; choose the **4–5**
   best-covered with strong genotype links. Likely shortlist: erythromycin, clindamycin,
   ciprofloxacin, gentamicin, tetracycline, oxacillin/cefoxitin (mecA showcase).
   Record the choice + counts in `docs/DECISIONS.md`.
3. **Labels rule** (`labels.py`): SIR → `R`/`S`; default **I → R** (conservative), but
   document and note sensitivity. If only MIC, apply CLSI/EUCAST breakpoints (documented
   table). One label per (genome_id, antibiotic).
4. **Drug DB** (`db/drugs_saureus.csv`): for each chosen drug fill class, `target_genes`
   (molecular target for the gate), `known_markers`, standardized name.

## Fallbacks
BV-BRC slow/flaky → use precomputed BV-BRC AMR tables, NCBI Pathogen Detection, or a
documented Kaggle mirror (record license/version/source). Never use unverified copies
without provenance.

## Definition of done
`labels.csv`, `manifest.csv`, FASTAs, and `drugs_saureus.csv` exist and validate against
DATA_SPEC; antibiotic choice + counts logged in DECISIONS.md; Person C can drop your
`labels.csv` in place of the synthetic one with no code change.

## Self-questioning before you call it done
Are any labels model-predicted rather than lab-measured? Are quality filters documented?
Is the I→R decision recorded with its rationale?
