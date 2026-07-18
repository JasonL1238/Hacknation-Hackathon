# Person B — Annotation & Feature Pipeline (Module 01)

> Read [CLAUDE.md](../../CLAUDE.md) and [docs/DATA_SPEC.md](../DATA_SPEC.md) first. Work on
> branch `feat/features`. **Never blocked** — dev on a handful of public NCBI *S. aureus*
> FASTAs immediately, swap to Person A's real genomes at integration.

## You own (edit freely)
- `src/genome_firewall/annotate.py`
- `src/genome_firewall/featurize.py`
- `data/interim/amrfinder/` (per-genome TSVs — gitignored)

## Deliverables (the contracts you produce)
1. **`data/processed/features.parquet`** — DATA_SPEC §1 (binary presence/absence matrix).
2. **`data/processed/feature_spec.json`** — DATA_SPEC §2 (frozen, ordered column list).

## Tasks
1. **Install AMRFinderPlus** into a dedicated env:
   `conda create -n amr -c conda-forge -c bioconda ncbi-amrfinderplus && conda activate amr && amrfinder -u`
   (fallback: Docker `ncbi/amr`). Record the DB version in `feature_spec.json`.
2. **Batch runner** (`annotate.py`): for each FASTA run
   `amrfinder -n contigs.fna --organism Staphylococcus_aureus --plus -o out.tsv`.
   The `--organism` flag is **mandatory** — it unlocks S. aureus point mutations
   (gyrA, grlA/parC, rpoB) and blaZ handling. Run in parallel; cache TSVs (skip if
   present) so reruns are cheap.
3. **Featurize** (`featurize.py`): parse each TSV → one row. Feature columns = **union
   across all genomes** of (a) gene symbols and (b) point mutations named as
   `gene_mutation` (e.g. `gyrA_S84L`). Absent = 0. Write `features.parquet` +
   `feature_spec.json` with a version hash of the sorted column list.
4. **Inference helper**: expose a function that, given a single FASTA, produces a feature
   vector **in `feature_spec.json` column order** (the Streamlit app will call this path).

## Fallbacks
AMRFinderPlus install/runtime trouble → Docker image; or, to unblock modeling, BV-BRC /
NCBI **precomputed** AMRFinderPlus results parsed into the same matrix schema.

## Definition of done
`features.parquet` + `feature_spec.json` validate against DATA_SPEC; the same code path
turns one uploaded FASTA into a spec-ordered vector; Person C can drop your matrix in
place of the synthetic one with no code change.

## Self-questioning before you call it done
Is `--organism Staphylococcus_aureus` set everywhere? Is the column order frozen and
versioned? Does single-genome inference produce a vector identical in shape/order to the
training matrix?
