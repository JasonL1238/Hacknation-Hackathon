#!/usr/bin/env python3
"""Build ESM-2-ready protein FASTAs from AMRFinderPlus nucleotide hits.

AMRFinderPlus was run on assembled nucleotide FASTAs, so its TSVs contain AMR-hit
coordinates but no amino-acid sequences. This script extracts those loci, respects
strand, translates with bacterial genetic code 11, and writes both per-genome FASTAs
and one combined FASTA. Record IDs always start with ``genome_id|`` so downstream
notebooks can recover the genome-to-protein mapping without guessing.
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

from Bio import SeqIO
from Bio.Seq import Seq


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RAW_DIR = REPO_ROOT / "data" / "raw"
DEFAULT_AMRFINDER_DIR = REPO_ROOT / "data" / "interim" / "amrfinder"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "data" / "interim" / "esm2_proteins"


def _safe_token(value: str) -> str:
    """Return a FASTA-ID-safe token while retaining recognizable marker names."""
    return re.sub(r"[^A-Za-z0-9_.+-]+", "_", value.strip()).strip("_") or "unknown"


def _translated_amr_records(genome_id: str, fasta_path: Path, tsv_path: Path):
    contigs = SeqIO.to_dict(SeqIO.parse(fasta_path, "fasta"))

    with tsv_path.open(newline="") as handle:
        rows = csv.DictReader(handle, delimiter="\t")
        required = {"Contig id", "Start", "Stop", "Strand", "Element symbol", "Type"}
        missing = required.difference(rows.fieldnames or [])
        if missing:
            raise ValueError(f"{tsv_path}: missing columns {sorted(missing)}")

        amr_index = 0
        for row in rows:
            if row["Type"] != "AMR":
                continue
            amr_index += 1
            contig_id = row["Contig id"]
            if contig_id not in contigs:
                raise KeyError(f"{tsv_path}: contig {contig_id!r} not found in {fasta_path}")

            start = int(row["Start"])
            stop = int(row["Stop"])
            left, right = sorted((start, stop))
            nucleotide = contigs[contig_id].seq[left - 1 : right]
            strand = row["Strand"]
            if strand == "-":
                nucleotide = nucleotide.reverse_complement()
            elif strand != "+":
                raise ValueError(f"{tsv_path}: unsupported strand {strand!r}")

            # Nearly all AMRFinder nucleotide hits are complete coding spans. A small
            # number of reported frameshift disruptions are not divisible by three;
            # trim the incomplete trailing codon and represent internal stops as X so
            # ESM-2 receives a valid amino-acid alphabet.
            nucleotide = nucleotide[: len(nucleotide) - (len(nucleotide) % 3)]
            if not nucleotide:
                continue
            protein = str(Seq(nucleotide).translate(table=11, to_stop=False))
            protein = protein.removesuffix("*").replace("*", "X")
            if not protein:
                continue

            symbol = _safe_token(row["Element symbol"])
            contig_token = _safe_token(contig_id)
            record_id = (
                f"{genome_id}|amr_{amr_index:03d}|{symbol}|"
                f"{contig_token}:{left}-{right}:{strand}"
            )
            yield record_id, protein


def write_fastas(raw_dir: Path, amrfinder_dir: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    combined_path = output_dir / "all_amr_proteins.faa"
    manifest_path = output_dir / "manifest.csv"

    fasta_paths = sorted(raw_dir.glob("*.fna"))
    if not fasta_paths:
        raise SystemExit(f"No genome FASTAs found under {raw_dir}")

    total_proteins = 0
    missing_tsvs: list[str] = []
    manifest_rows: list[dict[str, str | int]] = []

    with combined_path.open("w") as combined:
        for fasta_path in fasta_paths:
            genome_id = fasta_path.stem
            tsv_path = amrfinder_dir / f"{genome_id}.tsv"
            if not tsv_path.exists():
                missing_tsvs.append(genome_id)
                continue

            records = list(_translated_amr_records(genome_id, fasta_path, tsv_path))
            per_genome_path = output_dir / f"{genome_id}.faa"
            with per_genome_path.open("w") as per_genome:
                for record_id, protein in records:
                    entry = f">{record_id}\n{protein}\n"
                    per_genome.write(entry)
                    combined.write(entry)

            total_proteins += len(records)
            manifest_rows.append(
                {
                    "genome_id": genome_id,
                    "protein_count": len(records),
                    "fasta_file": per_genome_path.name,
                }
            )

    with manifest_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle, fieldnames=["genome_id", "protein_count", "fasta_file"]
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"Wrote {len(manifest_rows)} per-genome FASTAs to {output_dir}")
    print(f"Wrote {total_proteins} AMR protein sequences to {combined_path}")
    print(f"Wrote genome/protein mapping to {manifest_path}")
    if missing_tsvs:
        print(f"WARNING: {len(missing_tsvs)} genomes had no matching AMRFinder TSV")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--amrfinder-dir", type=Path, default=DEFAULT_AMRFINDER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_args()
    write_fastas(args.raw_dir, args.amrfinder_dir, args.output_dir)
