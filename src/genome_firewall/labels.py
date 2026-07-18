"""SIR -> binary R/S label rule (Stage 1, Module 01 data).

Reads the measured-label candidates written by `acquire.py`
(`data/interim/measured_labels.csv`) and produces `data/processed/labels.csv`
matching DATA_SPEC §3. No MIC/breakpoint conversion is needed: every row that
survives acquire.py's filter already carries a BV-BRC-assigned categorical SIR
phenotype, including the MIC-typed rows.
"""
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
INTERIM_DIR = REPO_ROOT / "data" / "interim"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"

# Conservative default: intermediate isolates are treated as resistant (patient-safety
# bias -- an "I" call should not be reported as "likely to work"). Matches
# config/saureus.yaml's `labels.intermediate_rule: R`.
SIR_TO_LABEL = {
    "Resistant": "R",
    "Intermediate": "R",
    "Susceptible": "S",
}


def build_labels(measured: pd.DataFrame) -> pd.DataFrame:
    df = measured.copy()
    df["label"] = df["resistant_phenotype"].map(SIR_TO_LABEL)
    assert df["label"].notna().all(), "unmapped phenotype value slipped through acquire.py's filter"

    n_before = len(df)
    dup_mask = df.duplicated(subset=["genome_id", "antibiotic"], keep=False)
    dup_pairs = df[dup_mask].groupby(["genome_id", "antibiotic"])["label"].nunique()
    conflicting = dup_pairs[dup_pairs > 1]
    if len(conflicting):
        print(
            f"WARNING: {len(conflicting)} (genome_id, antibiotic) pairs have "
            "conflicting measured labels across duplicate rows -- dropping both "
            "conflicting rows rather than guessing."
        )
        conflict_keys = set(conflicting.index)
        df = df[~df.set_index(["genome_id", "antibiotic"]).index.isin(conflict_keys)]

    # Remaining duplicates (same genome_id+antibiotic, same label from >1 row -- e.g.
    # re-tested with a second method) agree on the label, so the tie-break is
    # arbitrary: keep the first-seen row deterministically.
    df = df.drop_duplicates(subset=["genome_id", "antibiotic"], keep="first")
    print(f"labels: {n_before} candidate rows -> {len(df)} after de-dup/conflict handling")

    df["source"] = "BV-BRC"
    return df[["genome_id", "antibiotic", "label", "source", "method"]].reset_index(drop=True)


def run() -> None:
    measured = pd.read_csv(INTERIM_DIR / "measured_labels.csv", dtype=str)
    labels = build_labels(measured)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    out_path = PROCESSED_DIR / "labels.csv"
    labels.to_csv(out_path, index=False)
    print(f"wrote {out_path} ({len(labels)} rows, {labels['genome_id'].nunique()} genomes, "
          f"{labels['antibiotic'].nunique()} antibiotics)")


if __name__ == "__main__":
    run()
