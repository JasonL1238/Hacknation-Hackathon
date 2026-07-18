"""BV-BRC genome + AST acquisition (Stage 1, Module 01 data).

Filters the raw BV-BRC metadata pulls (`data/raw/BVBRC_genome.csv`,
`data/raw/BVBRC_genome_amr.csv`) down to lab-measured *S. aureus* AST rows on
good-quality genomes, picks the antibiotic shortlist, downloads the corresponding
contig FASTAs from the BV-BRC Data API, and writes the acquisition manifest.
"""
import hashlib
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
INTERIM_DIR = REPO_ROOT / "data" / "interim"

SPECIES = "Staphylococcus aureus"
GOOD_STATUS = {"Complete", "WGS"}
# Real, measured AST typing methods present in the BV-BRC pull (excludes rows with
# no method, which are typically computationally predicted phenotypes -- the brief
# requires lab-measured AST only).
MEASURED_METHODS = {
    "Broth dilution",
    "Disk diffusion",
    "Agar dilution",
    "MIC",
    "Biofosun Gram-positive panels broth dilution",
}
# "Nonsusceptible" is excluded: it's not a standard CLSI/EUCAST SIR category in this
# data and only covers 18 rows dataset-wide -- not worth a special-cased mapping.
CLEAN_PHENOTYPES = {"Resistant", "Susceptible", "Intermediate"}

MIN_CLASS_COUNT = 200  # min(#Resistant, #Susceptible) required to keep a candidate
TOP_K_ANTIBIOTICS = 6
# mecA/mecC-mediated methicillin resistance is read out here by three overlapping
# assays (oxacillin, cefoxitin, "methicillin"). Keeping more than one would just
# double-count a single biological signal as separate prediction targets. Cefoxitin
# is the current CLSI-preferred surrogate (more sensitive for heteroresistant/mecC
# strains) and has the best coverage of the three, so it's the one kept.
REDUNDANT_ANTIBIOTICS = {"oxacillin", "methicillin"}

BVBRC_SEQUENCE_API = "https://www.bv-brc.org/api/genome_sequence/"


def load_raw() -> tuple[pd.DataFrame, pd.DataFrame]:
    amr = pd.read_csv(RAW_DIR / "BVBRC_genome_amr.csv", dtype=str)
    genome = pd.read_csv(RAW_DIR / "BVBRC_genome.csv", dtype=str)
    return amr, genome


def filter_measured_labels(amr: pd.DataFrame, genome: pd.DataFrame) -> pd.DataFrame:
    """Species + measured-method + clean-phenotype + quality funnel.

    Returns one candidate-label row per (genome_id, antibiotic) with the raw SIR
    phenotype and typing method -- `labels.py` turns this into the final R/S label.
    """
    sa = genome[genome["Species"] == SPECIES]
    good_ids = set(
        sa.loc[
            (sa["Genome Quality"] == "Good") & (sa["Genome Status"].isin(GOOD_STATUS)),
            "Genome ID",
        ]
    )
    sa_ids = set(sa["Genome ID"])

    n0 = len(amr)
    f = amr[amr["Genome ID"].isin(sa_ids)]
    n1 = len(f)
    f = f[f["Laboratory Typing Method"].isin(MEASURED_METHODS)]
    n2 = len(f)
    f = f[f["Resistant Phenotype"].isin(CLEAN_PHENOTYPES)]
    n3 = len(f)
    f = f[f["Genome ID"].isin(good_ids)]
    n4 = len(f)
    print(
        f"filter funnel: all={n0} -> S.aureus={n1} -> measured-method={n2} "
        f"-> clean-phenotype={n3} -> good-quality={n4}"
    )

    return f[
        ["Genome ID", "Antibiotic", "Resistant Phenotype", "Laboratory Typing Method"]
    ].rename(
        columns={
            "Genome ID": "genome_id",
            "Antibiotic": "antibiotic",
            "Resistant Phenotype": "resistant_phenotype",
            "Laboratory Typing Method": "method",
        }
    )


def select_antibiotics(filtered: pd.DataFrame) -> pd.DataFrame:
    """Rank antibiotics by clean-label coverage, keep only ones with enough of both
    classes to split/calibrate/hold out, drop mechanistically-redundant duplicates,
    and return the top-K by total count. Returns the ranking table (all candidates,
    with a `selected` column) so the decision is auditable, not just the shortlist.
    """
    counts = (
        filtered.groupby(["antibiotic", "resistant_phenotype"])
        .size()
        .unstack(fill_value=0)
    )
    for col in ("Resistant", "Susceptible", "Intermediate"):
        if col not in counts:
            counts[col] = 0
    counts["min_class"] = counts[["Resistant", "Susceptible"]].min(axis=1)
    counts["total"] = counts[["Resistant", "Susceptible", "Intermediate"]].sum(axis=1)
    counts = counts.sort_values("total", ascending=False)

    eligible = counts[counts["min_class"] >= MIN_CLASS_COUNT]
    eligible = eligible.drop(
        index=[a for a in REDUNDANT_ANTIBIOTICS if a in eligible.index]
    )
    shortlist = set(eligible.head(TOP_K_ANTIBIOTICS).index)

    counts["selected"] = counts.index.isin(shortlist)
    return counts


def _fetch_fasta(genome_id: str, session: requests.Session, retries: int = 3) -> str:
    url = f"{BVBRC_SEQUENCE_API}?eq(genome_id,{genome_id})&limit(1000)"
    headers = {"Accept": "application/dna+fasta"}
    last_exc = None
    for attempt in range(retries):
        try:
            resp = session.get(url, headers=headers, timeout=60)
            resp.raise_for_status()
            if resp.text.strip():
                return resp.text
            raise ValueError("empty response body")
        except Exception as exc:  # network hiccup -- retry with backoff
            last_exc = exc
            time.sleep(2**attempt)
    raise RuntimeError(f"failed to fetch {genome_id}: {last_exc}")


def download_fastas(
    genome_ids: list[str], out_dir: Path = RAW_DIR, max_workers: int = 8
) -> tuple[list[dict], list[tuple[str, str]]]:
    """Download contig FASTAs for genome_ids not already present in out_dir.

    Returns (rows, failed) where rows have {genome_id, fasta_path, checksum} for
    every genome_id now on disk (freshly downloaded or pre-existing), and failed
    has (genome_id, error) for ones that could not be fetched after retries.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    rows, failed = [], []

    def _one(genome_id: str):
        fasta_path = out_dir / f"{genome_id}.fna"
        if fasta_path.exists() and fasta_path.stat().st_size > 0:
            return genome_id, fasta_path, None
        try:
            text = _fetch_fasta(genome_id, session)
            fasta_path.write_text(text)
            return genome_id, fasta_path, None
        except Exception as exc:
            return genome_id, None, str(exc)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_one, gid): gid for gid in genome_ids}
        for fut in as_completed(futures):
            genome_id, fasta_path, err = fut.result()
            if err:
                failed.append((genome_id, err))
            else:
                checksum = hashlib.sha256(fasta_path.read_bytes()).hexdigest()
                rows.append(
                    {
                        "genome_id": genome_id,
                        "fasta_path": str(fasta_path.relative_to(REPO_ROOT)),
                        "checksum": checksum,
                    }
                )
    return rows, failed


def build_manifest(
    download_rows: list[dict], genome: pd.DataFrame
) -> pd.DataFrame:
    meta = genome.set_index("Genome ID")[
        ["Assembly Accession", "GenBank Accessions", "Genome Status", "Genome Quality"]
    ]
    manifest = pd.DataFrame(download_rows).set_index("genome_id")
    manifest = manifest.join(meta, how="left")
    manifest["source"] = "BV-BRC"
    manifest["quality_flags"] = (
        manifest["Genome Status"].fillna("") + ";" + manifest["Genome Quality"].fillna("")
    )
    manifest = manifest.rename(
        columns={"Assembly Accession": "accession", "GenBank Accessions": "genbank_accessions"}
    )
    return manifest[
        ["accession", "genbank_accessions", "source", "checksum", "quality_flags"]
    ].reset_index()


def run() -> None:
    amr, genome = load_raw()
    filtered = filter_measured_labels(amr, genome)

    ranking = select_antibiotics(filtered)
    print(ranking[["Resistant", "Susceptible", "Intermediate", "total", "min_class", "selected"]])

    chosen = ranking[ranking["selected"]].index.tolist()
    candidate_labels = filtered[filtered["antibiotic"].isin(chosen)]

    INTERIM_DIR.mkdir(parents=True, exist_ok=True)
    candidate_labels.to_csv(INTERIM_DIR / "measured_labels.csv", index=False)

    genome_ids = sorted(candidate_labels["genome_id"].unique())
    print(f"downloading {len(genome_ids)} FASTAs for {len(chosen)} antibiotics: {chosen}")
    rows, failed = download_fastas(genome_ids)
    if failed:
        print(f"WARNING: {len(failed)} genomes failed to download and were dropped:")
        for gid, err in failed[:20]:
            print(f"  {gid}: {err}")

    manifest = build_manifest(rows, genome)
    manifest.to_csv(RAW_DIR / "manifest.csv", index=False)
    print(f"wrote manifest.csv with {len(manifest)} genomes")


if __name__ == "__main__":
    run()
