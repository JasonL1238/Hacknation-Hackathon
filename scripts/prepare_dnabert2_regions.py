#!/usr/bin/env python3
"""Build a DNABERT-2-ready FASTA of AMRFinderPlus AMR loci plus flanking DNA.

Each output FASTA record is one AMRFinderPlus row where ``Type == AMR``. The
corresponding manifest records the genome ID, original locus coordinates, extracted
window coordinates, strand, and sequence length. Minus-strand windows are reverse
complemented so every region is oriented in the gene's 5'→3' direction.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from Bio import SeqIO


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_AMRFINDER_DIR = REPO_ROOT / "data" / "interim" / "amrfinder"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "interim" / "dnabert2_regions"


def _safe_token(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", value.strip()).strip("_") or "unknown"


def _amr_rows(tsv_path: Path):
    with tsv_path.open(newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        required = {"Contig id", "Start", "Stop", "Strand", "Element symbol", "Type"}
        missing = required.difference(rows.fieldnames or [])
        if missing:
            raise ValueError(f"{tsv_path}: missing columns {sorted(missing)}")
        yield from (row for row in rows if row["Type"] == "AMR")


def write_regions(raw_dir: Path, amrfinder_dir: Path, output_dir: Path, flank: int) -> None:
    if flank < 0:
        raise ValueError("flank must be non-negative")
    fasta_paths = sorted(raw_dir.glob("*.fna"))
    if not fasta_paths:
        raise SystemExit(f"No genome FASTAs found under {raw_dir}")

    output_dir.mkdir(parents=True, exist_ok=True)
    fasta_out = output_dir / "amr_regions.fasta"
    manifest_out = output_dir / "manifest.csv"
    manifest_rows: list[dict[str, str | int]] = []
    missing_tsvs: list[str] = []
    total_regions = 0

    with fasta_out.open("w") as output_handle:
        for fasta_path in fasta_paths:
            genome_id = fasta_path.stem
            tsv_path = amrfinder_dir / f"{genome_id}.tsv"
            if not tsv_path.exists():
                missing_tsvs.append(genome_id)
                continue

            contigs = SeqIO.to_dict(SeqIO.parse(fasta_path, "fasta"))
            for region_index, row in enumerate(_amr_rows(tsv_path), start=1):
                contig_id = row["Contig id"]
                if contig_id not in contigs:
                    raise KeyError(
                        f"{tsv_path}: contig {contig_id!r} not found in {fasta_path}"
                    )
                locus_start, locus_stop = sorted((int(row["Start"]), int(row["Stop"])))
                contig = contigs[contig_id]
                window_start = max(1, locus_start - flank)
                window_stop = min(len(contig.seq), locus_stop + flank)
                sequence = contig.seq[window_start - 1 : window_stop]

                strand = row["Strand"]
                if strand == "-":
                    sequence = sequence.reverse_complement()
                elif strand != "+":
                    raise ValueError(f"{tsv_path}: unsupported strand {strand!r}")

                symbol = _safe_token(row["Element symbol"])
                contig_token = _safe_token(contig_id)
                region_id = (
                    f"{genome_id}|region_{region_index:03d}|{symbol}|"
                    f"{contig_token}:{window_start}-{window_stop}:{strand}|flank_{flank}"
                )
                output_handle.write(f">{region_id}\n{sequence}\n")
                manifest_rows.append(
                    {
                        "region_id": region_id,
                        "genome_id": genome_id,
                        "element_symbol": row["Element symbol"],
                        "contig_id": contig_id,
                        "strand": strand,
                        "locus_start": locus_start,
                        "locus_stop": locus_stop,
                        "window_start": window_start,
                        "window_stop": window_stop,
                        "flank_bp": flank,
                        "sequence_length": len(sequence),
                        "fasta_file": fasta_out.name,
                    }
                )
                total_regions += 1

    fieldnames = [
        "region_id",
        "genome_id",
        "element_symbol",
        "contig_id",
        "strand",
        "locus_start",
        "locus_stop",
        "window_start",
        "window_stop",
        "flank_bp",
        "sequence_length",
        "fasta_file",
    ]
    with manifest_out.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Wrote {total_regions} AMR DNA regions to {fasta_out}")
    print(f"Wrote region manifest to {manifest_out}")
    if missing_tsvs:
        print(f"WARNING: {len(missing_tsvs)} genomes had no matching AMRFinder TSV")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--amrfinder-dir", type=Path, default=DEFAULT_AMRFINDER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--flank", type=int, default=200, help="bases on each side of a locus")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    write_regions(args.raw_dir, args.amrfinder_dir, args.output_dir, args.flank)
