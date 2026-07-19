"""Parse AMRFinderPlus TSVs into the presence/absence feature matrix (Stage 2, Module 01).

Produces `data/processed/features.parquet` (DATA_SPEC §1) and
`data/processed/feature_spec.json` (DATA_SPEC §2), and exposes `vectorize_fasta` — the
single-genome inference path the Streamlit demo calls, which builds a feature vector in
the exact frozen column order.

Feature policy (see docs/DECISIONS.md): only `Type == "AMR"` rows become features.
VIRULENCE and STRESS/BIOCIDE/METAL rows are excluded — presenting a virulence or
biocide-tolerance gene as an antibiotic-resistance feature would be a causation
overclaim. AMRFinderPlus v4 already encodes point mutations in `Element symbol`
(e.g. `gyrA_S84L`), so the symbol is used directly as the feature key for both genes
and mutations.
"""
import hashlib
import json
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from genome_firewall import annotate

REPO_ROOT = Path(__file__).resolve().parents[2]
AMRFINDER_DIR = REPO_ROOT / "data" / "interim" / "amrfinder"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FEATURES_PATH = PROCESSED_DIR / "features.parquet"
SPEC_PATH = PROCESSED_DIR / "feature_spec.json"

ORGANISM_FLAG = "Staphylococcus_aureus"


def parse_tsv(tsv_path: Path) -> set[str]:
    """Return the set of AMR feature symbols present in one AMRFinderPlus TSV."""
    df = pd.read_csv(tsv_path, sep="\t", dtype=str)
    if df.empty or "Type" not in df.columns:
        return set()
    amr = df[df["Type"] == "AMR"]
    return set(amr["Element symbol"].dropna())


def build_matrix(tsv_paths: list[Path]) -> tuple[pd.DataFrame, list[str]]:
    per_genome = {p.stem: parse_tsv(p) for p in tsv_paths}
    columns = sorted({sym for syms in per_genome.values() for sym in syms})
    rows = {
        gid: [1 if sym in syms else 0 for sym in columns]
        for gid, syms in per_genome.items()
    }
    matrix = pd.DataFrame.from_dict(rows, orient="index", columns=columns).astype("int8")
    matrix.index.name = "genome_id"
    matrix = matrix.sort_index()
    return matrix, columns


def _spec_version(columns: list[str]) -> str:
    payload = "\n".join(columns).encode()
    return "sha256-" + hashlib.sha256(payload).hexdigest()


def write_spec(columns: list[str], db_version: str) -> dict:
    spec = {
        "version": _spec_version(columns),
        "columns": columns,
        "amrfinder_db_version": db_version,
        "organism_flag": ORGANISM_FLAG,
    }
    SPEC_PATH.write_text(json.dumps(spec, indent=2))
    return spec


def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def extract_fasta_features(
    fasta_path: str | Path, spec: dict | None = None
) -> tuple[pd.Series, set[str]]:
    """Annotate one FASTA and return its frozen vector plus every AMR symbol found."""
    spec = spec or load_spec()
    fasta_path = Path(fasta_path)
    actual_db = annotate.amrfinder_db_version()
    expected_db = str(spec.get("amrfinder_db_version", "")).strip()
    if expected_db and actual_db != expected_db:
        raise RuntimeError(
            "AMRFinderPlus database mismatch: "
            f"model requires {expected_db}, but runtime provides {actual_db}."
        )
    with tempfile.TemporaryDirectory() as tmp:
        out_tsv = Path(tmp) / "out.tsv"
        completed = subprocess.run(
            [
                *annotate.amrfinder_command(),
                "-n", str(fasta_path),
                "--organism", ORGANISM_FLAG,
                "--plus",
                "--threads", str(annotate.THREADS_PER_JOB),
                "-o", str(out_tsv),
            ],
            capture_output=True, text=True,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise RuntimeError(f"AMRFinderPlus annotation failed: {detail[:1000]}")
        present = parse_tsv(out_tsv)
    vector = pd.Series(
        [1 if col in present else 0 for col in spec["columns"]],
        index=spec["columns"], dtype="int8", name=fasta_path.stem,
    )
    return vector, present


def vectorize_fasta(fasta_path: str | Path, spec: dict | None = None) -> pd.Series:
    """Inference vector in frozen training-column order; unseen symbols are ignored."""
    vector, _ = extract_fasta_features(fasta_path, spec)
    return vector


def run() -> None:
    tsv_paths = sorted(AMRFINDER_DIR.glob("*.tsv"))
    if not tsv_paths:
        raise SystemExit("no AMRFinderPlus TSVs found — run `make annotate` first")

    matrix, columns = build_matrix(tsv_paths)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    matrix.to_parquet(FEATURES_PATH)
    spec = write_spec(columns, annotate.amrfinder_db_version())

    print(f"wrote {FEATURES_PATH}: {matrix.shape[0]} genomes x {matrix.shape[1]} features")
    print(f"wrote {SPEC_PATH}: version {spec['version'][:20]}..., db {spec['amrfinder_db_version']}")
    top = matrix.sum().sort_values(ascending=False).head(15)
    print("most common features:\n" + top.to_string())


if __name__ == "__main__":
    run()
