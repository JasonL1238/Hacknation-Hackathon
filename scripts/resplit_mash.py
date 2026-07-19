"""Download genome FASTAs listed in the acquisition manifest, verify them against
the recorded checksums, then re-run the grouped split on real Mash/ANI sequence
homology (instead of the AMR-feature-Jaccard fallback).

The genome id list + expected sha256 checksums come from data/raw/manifest.csv, so
this does NOT need the raw BV-BRC metadata CSVs (which aren't all on disk). After the
FASTAs land, `genome_firewall.split.run()` auto-detects `mash` on PATH and uses it.

Usage:
    python -m scripts.resplit_mash            # download all, verify, re-split
    python -m scripts.resplit_mash --no-split # download + verify only
"""
import argparse
import hashlib
import sys
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from genome_firewall import acquire, split  # noqa: E402

MANIFEST = REPO_ROOT / "data" / "raw" / "manifest.csv"


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download_and_verify() -> None:
    manifest = pd.read_csv(MANIFEST, dtype=str)
    expected = dict(zip(manifest["genome_id"], manifest["checksum"]))
    genome_ids = sorted(expected)
    print(f"manifest: {len(genome_ids)} genomes to ensure on disk")

    rows, failed = acquire.download_fastas(genome_ids)
    print(f"on disk: {len(rows)}  |  download failures: {len(failed)}")
    for gid, err in failed[:20]:
        print(f"  FAILED {gid}: {err}")

    # Verify freshly-downloaded + pre-existing FASTAs against the manifest checksums.
    mismatched, missing = [], []
    for gid in genome_ids:
        fna = acquire.RAW_DIR / f"{gid}.fna"
        if not fna.exists() or fna.stat().st_size == 0:
            missing.append(gid)
            continue
        if expected[gid] and _checksum(fna) != expected[gid]:
            mismatched.append(gid)
    print(f"checksum: {len(genome_ids) - len(missing) - len(mismatched)} ok, "
          f"{len(mismatched)} mismatched, {len(missing)} missing")
    for gid in mismatched[:20]:
        print(f"  CHECKSUM MISMATCH {gid}")
    if missing or mismatched:
        print("WARNING: not every genome is present + verified; the mash split will "
              "fall back to feature-jaccard for the whole run if ANY FASTA is missing "
              "(see split._mash_distance_matrix).")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-split", action="store_true", help="download + verify only")
    ap.add_argument("--cluster-threshold", type=float, default=None,
                    help="override mash cluster distance threshold (default 0.002)")
    args = ap.parse_args()

    download_and_verify()
    if args.no_split:
        return
    print("=" * 70)
    print("re-running split (mash auto-detected if all FASTAs present) ...")
    split.run(cluster_threshold=args.cluster_threshold)


if __name__ == "__main__":
    main()
