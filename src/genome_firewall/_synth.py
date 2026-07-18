"""Synthetic data generator — the shared seam that unblocks parallel work.

Emits schema-valid FAKE versions of the contract files in docs/DATA_SPEC.md
(features.parquet, feature_spec.json, labels.csv, splits.json, a placeholder
db/drugs_saureus.csv, and a sample report object) so Person C and Person D can
build and test their entire pipeline before Person A's real labels or Person
B's real features exist.

Real outputs from A/B/C are written to these exact same paths and simply
overwrite these placeholders — no code downstream needs to change. Run:

    python -m genome_firewall._synth          # writes only files that don't exist yet
    python -m genome_firewall._synth --force   # regenerates everything, even if present

Do not change these schemas without a team sync — see docs/DATA_SPEC.md.
"""

import argparse
import csv
import hashlib
import json
import random
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
DRUGS_DB = REPO_ROOT / "db" / "drugs_saureus.csv"

RNG_SEED = 1280  # S. aureus taxon id, for a stable and memorable seed

N_GENOMES = 24
N_CLUSTERS = 6
SPLIT_FRACTIONS = {"train": 0.6, "cal": 0.15, "test": 0.25}

# A representative S. aureus AMR feature set: acquired genes + catalogued point
# mutations, matching the mechanisms called out in PLAN.md / CLAUDE.md.
FEATURE_COLUMNS = [
    "mecA", "mecC", "blaZ",
    "ermA", "ermB", "ermC",
    "tetK", "tetM",
    "aac6_aph2",
    "gyrA_S84L", "grlA_S80F",
    "rpoB_H481Y",
    "vanA", "dfrG",
]

# The plan's expected best-covered antibiotic shortlist, with the acquired
# gene/mutation(s) that plausibly drive resistance for each — used only to
# make synthetic labels feel biologically coherent, not as ground truth.
ANTIBIOTICS = {
    "oxacillin":     {"drug_class": "beta-lactam",      "target_genes": "pbp2",  "markers": ["mecA", "mecC"]},
    "erythromycin":  {"drug_class": "macrolide",         "target_genes": "rplD",  "markers": ["ermA", "ermB", "ermC"]},
    "clindamycin":   {"drug_class": "lincosamide",       "target_genes": "rplD",  "markers": ["ermA", "ermB", "ermC"]},
    "ciprofloxacin": {"drug_class": "fluoroquinolone",   "target_genes": "gyrA;grlA", "markers": ["gyrA_S84L", "grlA_S80F"]},
    "gentamicin":    {"drug_class": "aminoglycoside",    "target_genes": "rrs",   "markers": ["aac6_aph2"]},
    "tetracycline":  {"drug_class": "tetracycline",      "target_genes": "rpsJ",  "markers": ["tetK", "tetM"]},
}


def _feature_spec():
    columns = sorted(FEATURE_COLUMNS)
    version = hashlib.sha256(",".join(columns).encode()).hexdigest()[:16]
    return {
        "version": f"sha256-{version}",
        "columns": columns,
        "amrfinder_db_version": "synthetic-0.0",
        "organism_flag": "Staphylococcus_aureus",
    }


def _genome_ids():
    return [f"SYN.{i:04d}" for i in range(1, N_GENOMES + 1)]


def _assign_clusters(genome_ids, rng):
    # Whole clusters, never individual genomes, get assigned to a split —
    # mirrors the real grouped-split invariant enforced later by split.py.
    per_cluster = len(genome_ids) // N_CLUSTERS
    clusters = {}
    for i, gid in enumerate(genome_ids):
        clusters[gid] = min(i // per_cluster, N_CLUSTERS - 1)
    return clusters


def _split_for_clusters(rng):
    cluster_ids = list(range(N_CLUSTERS))
    rng.shuffle(cluster_ids)
    n_train = round(N_CLUSTERS * SPLIT_FRACTIONS["train"])
    n_cal = round(N_CLUSTERS * SPLIT_FRACTIONS["cal"])
    assignment = {}
    for i, cid in enumerate(cluster_ids):
        if i < n_train:
            assignment[cid] = "train"
        elif i < n_train + n_cal:
            assignment[cid] = "cal"
        else:
            assignment[cid] = "test"
    return assignment


def build_splits(rng):
    genome_ids = _genome_ids()
    cluster_of = _assign_clusters(genome_ids, rng)
    split_of_cluster = _split_for_clusters(rng)
    return {
        gid: {"split": split_of_cluster[cluster_of[gid]], "cluster_id": cluster_of[gid]}
        for gid in genome_ids
    }


def build_features(genome_ids, rng):
    columns = _feature_spec()["columns"]
    rows = {}
    for gid in genome_ids:
        # Each genome carries a handful of plausible resistance markers,
        # not pure noise, so downstream calibration has real signal to fit.
        rows[gid] = {col: int(rng.random() < 0.3) for col in columns}
    df = pd.DataFrame.from_dict(rows, orient="index", columns=columns).astype("int8")
    df.index.name = "genome_id"
    return df


def build_labels(features_df, rng):
    records = []
    for gid, row in features_df.iterrows():
        for antibiotic, info in ANTIBIOTICS.items():
            has_marker = any(row.get(m, 0) == 1 for m in info["markers"])
            # 90% consistent with markers, 10% flipped, so the model has to
            # earn its calibration rather than fit a deterministic rule.
            resistant = has_marker if rng.random() < 0.9 else not has_marker
            records.append({
                "genome_id": gid,
                "antibiotic": antibiotic,
                "label": "R" if resistant else "S",
                "source": "SYNTHETIC",
                "method": "synthetic",
            })
    return pd.DataFrame.from_records(records)


def write_drugs_db(force):
    if DRUGS_DB.exists() and not force:
        print(f"skip (exists): {DRUGS_DB.relative_to(REPO_ROOT)}")
        return
    DRUGS_DB.parent.mkdir(parents=True, exist_ok=True)
    with open(DRUGS_DB, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["antibiotic", "drug_class", "target_genes", "known_markers", "standardized_name"])
        for antibiotic, info in ANTIBIOTICS.items():
            writer.writerow([
                antibiotic,
                info["drug_class"],
                info["target_genes"],
                ";".join(info["markers"]),
                antibiotic.capitalize(),
            ])
    print(f"wrote (placeholder — Person A owns the real version): {DRUGS_DB.relative_to(REPO_ROOT)}")


def build_sample_report(features_df, labels_df, feature_spec):
    # Pick the genome with the most markers present as the "interesting" demo case.
    gid = features_df.sum(axis=1).idxmax()
    row = features_df.loc[gid]
    present = [col for col in feature_spec["columns"] if row[col] == 1]

    report = []
    for antibiotic, info in ANTIBIOTICS.items():
        hits = [m for m in info["markers"] if m in present]
        label = labels_df[(labels_df.genome_id == gid) & (labels_df.antibiotic == antibiotic)]["label"].iloc[0]
        if hits:
            verdict = "fail" if label == "R" else "work"
            evidence_category = "i"
            confidence = 0.9 if verdict == "fail" else 0.75
            reasons = [f"{m} detected (known {antibiotic} resistance determinant)" for m in hits]
        else:
            verdict = "work" if label == "S" else "nocall"
            evidence_category = "iii" if verdict == "nocall" else "ii"
            confidence = 0.5 if verdict == "nocall" else 0.6
            reasons = ["no known resistance marker detected"]
        report.append({
            "antibiotic": antibiotic,
            "verdict": verdict,
            "confidence": confidence,
            "evidence_category": evidence_category,
            "supporting_features": hits,
            "target_present": True,
            "reasons": reasons,
        })
    return {"genome_id": gid, "report": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="overwrite files even if they already exist")
    args = parser.parse_args()

    PROCESSED.mkdir(parents=True, exist_ok=True)
    rng = random.Random(RNG_SEED)

    feature_spec = _feature_spec()
    genome_ids = _genome_ids()
    features_df = build_features(genome_ids, rng)
    labels_df = build_labels(features_df, rng)
    splits = build_splits(rng)
    sample_report = build_sample_report(features_df, labels_df, feature_spec)

    targets = {
        PROCESSED / "features.parquet": lambda: features_df.to_parquet(PROCESSED / "features.parquet"),
        PROCESSED / "feature_spec.json": lambda: (PROCESSED / "feature_spec.json").write_text(json.dumps(feature_spec, indent=2)),
        PROCESSED / "labels.csv": lambda: labels_df.to_csv(PROCESSED / "labels.csv", index=False),
        PROCESSED / "splits.json": lambda: (PROCESSED / "splits.json").write_text(json.dumps(splits, indent=2)),
        PROCESSED / "sample_report.json": lambda: (PROCESSED / "sample_report.json").write_text(json.dumps(sample_report, indent=2)),
    }
    for path, write in targets.items():
        if path.exists() and not args.force:
            print(f"skip (exists): {path.relative_to(REPO_ROOT)}")
            continue
        write()
        print(f"wrote: {path.relative_to(REPO_ROOT)}")

    write_drugs_db(args.force)


if __name__ == "__main__":
    main()
