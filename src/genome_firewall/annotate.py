"""Batch AMRFinderPlus runner (Stage 2, Module 01).

Runs `amrfinder -n <fasta> --organism Staphylococcus_aureus --plus` over every FASTA
in `data/raw/`, caching one TSV per genome under `data/interim/amrfinder/`. The
`--organism` flag is mandatory: it unlocks S. aureus point-mutation detection (gyrA,
grlA/parC, rpoB) and blaZ handling.

AMRFinderPlus may live directly in the active deployment environment or in the local
separate conda env `amr` created by `scripts/setup_amrfinder.sh`.
"""
import subprocess
import shutil
import os
import tempfile
import threading
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
AMRFINDER_DIR = REPO_ROOT / "data" / "interim" / "amrfinder"

AMR_ENV = "amr"
ORGANISM = "Staphylococcus_aureus"
THREADS_PER_JOB = 2
RUNTIME_DB_ROOT = Path(tempfile.gettempdir()) / "bioshield-amrfinder-data"
_DB_SETUP_LOCK = threading.Lock()


def amrfinder_command() -> list[str]:
    """Return a command prefix for local conda or container installations."""
    direct = shutil.which("amrfinder")
    if direct:
        return [direct]
    conda = shutil.which("conda")
    if conda:
        return [conda, "run", "-n", AMR_ENV, "amrfinder"]
    raise RuntimeError(
        "AMRFinderPlus is not installed. Create environment.yml or run `make amr-setup`."
    )


def amrfinder_update_command() -> list[str]:
    """Return the matching database-updater command prefix."""

    direct = shutil.which("amrfinder_update")
    if direct:
        return [direct]
    conda = shutil.which("conda")
    if conda:
        return [conda, "run", "-n", AMR_ENV, "amrfinder_update"]
    raise RuntimeError(
        "amrfinder_update is not installed with AMRFinderPlus. "
        "Create environment.yml or run `make amr-setup`."
    )


def _installed_db_version() -> str:
    completed = subprocess.run(
        [*amrfinder_command(), "--database_version"],
        capture_output=True, text=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "unknown error").strip()
        raise RuntimeError(f"AMRFinderPlus database is unavailable: {detail[:1000]}")
    out = completed.stdout
    for line in out.splitlines():
        if line.startswith("Database version:"):
            return line.split(":", 1)[1].strip()
    return "unknown"


def amrfinder_db_version() -> str:
    """Return the database version, provisioning the runtime database if absent.

    Bioconda installs the AMRFinderPlus executable but not necessarily its database.
    Streamlit instances therefore download the database lazily into temporary server
    storage. ``featurize.extract_fasta_features`` still rejects any version that does
    not exactly match the model's frozen feature specification.
    """

    try:
        return _installed_db_version()
    except RuntimeError:
        pass

    with _DB_SETUP_LOCK:
        # Another request may have completed setup while this one waited.
        try:
            return _installed_db_version()
        except RuntimeError:
            pass

        db_root = Path(
            os.environ.get("BIOSHIELD_AMRFINDER_DATA_ROOT", str(RUNTIME_DB_ROOT))
        )
        db_root.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [*amrfinder_update_command(), "--database", str(db_root)],
            capture_output=True, text=True, timeout=900,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "unknown error").strip()
            raise RuntimeError(
                "AMRFinderPlus database provisioning failed: " + detail[:1000]
            )

        latest = db_root / "latest"
        os.environ["AMRFINDER_DB"] = str(latest if latest.exists() else db_root)
        return _installed_db_version()


def _annotate_one(fasta_path: Path) -> tuple[str, str | None]:
    genome_id = fasta_path.stem
    out_tsv = AMRFINDER_DIR / f"{genome_id}.tsv"
    if out_tsv.exists() and out_tsv.stat().st_size > 0:
        return genome_id, None
    tmp_tsv = out_tsv.with_suffix(".tsv.partial")
    cmd = [
        *amrfinder_command(),
        "-n", str(fasta_path),
        "--organism", ORGANISM,
        "--plus",
        "--threads", str(THREADS_PER_JOB),
        "-o", str(tmp_tsv),
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, check=True)
        tmp_tsv.replace(out_tsv)  # atomic: only a complete run leaves a .tsv
        return genome_id, None
    except subprocess.CalledProcessError as exc:
        tmp_tsv.unlink(missing_ok=True)
        return genome_id, (exc.stderr or exc.stdout or str(exc)).strip()[:500]


def run(max_workers: int = 4) -> None:
    AMRFINDER_DIR.mkdir(parents=True, exist_ok=True)
    fastas = sorted(RAW_DIR.glob("*.fna"))
    todo = [f for f in fastas if not (AMRFINDER_DIR / f"{f.stem}.tsv").exists()]
    print(f"{len(fastas)} FASTAs, {len(fastas) - len(todo)} already annotated, "
          f"{len(todo)} to run (db {amrfinder_db_version()})")

    failed = []
    with ProcessPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_annotate_one, f): f for f in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            genome_id, err = fut.result()
            if err:
                failed.append((genome_id, err))
            if i % 50 == 0 or i == len(todo):
                print(f"  annotated {i}/{len(todo)} (failed so far: {len(failed)})")

    if failed:
        print(f"WARNING: {len(failed)} genomes failed AMRFinderPlus:")
        for gid, err in failed[:20]:
            print(f"  {gid}: {err}")


if __name__ == "__main__":
    run()
