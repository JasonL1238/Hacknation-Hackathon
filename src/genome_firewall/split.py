"""Grouped, leakage-free train/cal/test split (Stage 3, Module 01 modeling).

S. aureus is highly clonal: a large share of the genomes in this collection share
byte-identical or near-identical AMR feature profiles (shared lineages). Randomly
splitting genomes would place near-duplicates of the same strain across train and
test, so every downstream accuracy/calibration number would really be measuring
memorization of a lineage the model already saw, not generalization. This module
groups genomes into genetic clusters first and then assigns *whole clusters* to a
split, so no cluster -- and therefore no near-duplicate genome -- ever spans splits
(DATA_SPEC.md #4, CLAUDE.md rigor rule 1).

Clustering prefers genome-level Mash/ANI distance (the real phylogenetic signal) and
falls back to Jaccard distance over `features.parquet` (the AMR presence/absence
matrix) when `mash` isn't on PATH. The feature-based fallback is coarser: it can only
catch genomes with identical gene content, and it clusters directly on the same
signal the model consumes as X, which is conservative (over-clusters convergent gene
content rather than missing a true lineage leak) but is not a substitute for real
ANI. Clusters are cross-checked against BV-BRC's MLST calls where available so a
skeptical read of this file has an independent signal to check the AMR-only proxy
against, not just this script's own say-so.
"""
import argparse
import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.cluster.hierarchy import fcluster, linkage
from scipy.spatial.distance import pdist, squareform

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FEATURES_PATH = PROCESSED_DIR / "features.parquet"
LABELS_PATH = PROCESSED_DIR / "labels.csv"
BVBRC_GENOME_PATH = RAW_DIR / "BVBRC_genome.csv"
SPLITS_PATH = PROCESSED_DIR / "splits.json"

# Exact-match only. With a ~144-dim binary AMR feature vector there is no principled
# "near enough" threshold above zero the way there is for true ANI: any nonzero
# Jaccard distance is a real difference in detected gene content, not assembly noise.
FEATURE_DEDUP_THRESHOLD = 0.0
FEATURE_CLUSTER_THRESHOLD = 0.05

MASH_DEDUP_THRESHOLD = 0.0002  # ANI >= 99.98%
MASH_CLUSTER_THRESHOLD = 0.002  # coarser than dedup; tune ~0.001-0.005

TARGET_SPLIT_FRACTIONS = {"train": 0.70, "cal": 0.15, "test": 0.15}
MIN_HELDOUT_CLUSTERS = 5  # smallest clusters forced entirely out of train


def _mash_distance_matrix(genome_ids: list[str]) -> np.ndarray | None:
    """Condensed Mash distance matrix over the genomes' assembled FASTAs, or None if
    `mash` isn't on PATH or any genome's FASTA can't be found (caller falls back to
    the feature-based proxy for the whole run rather than mixing distance sources).
    """
    if shutil.which("mash") is None:
        print("mash: not found on PATH")
        return None

    fasta_paths = []
    missing = []
    for gid in genome_ids:
        hits = list(RAW_DIR.glob(f"{gid}.fna")) + list(RAW_DIR.glob(f"{gid}.fasta"))
        if not hits:
            missing.append(gid)
        else:
            fasta_paths.append(hits[0])
    if missing:
        print(f"mash: {len(missing)} genome(s) have no FASTA on disk "
              f"(e.g. {missing[:5]}) -- falling back to feature-based distance for "
              f"the whole run so every genome still gets a cluster assignment")
        return None

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        list_path = tmp / "genomes.txt"
        list_path.write_text("\n".join(str(p) for p in fasta_paths))
        sketch_prefix = tmp / "sketch"
        subprocess.run(
            ["mash", "sketch", "-o", str(sketch_prefix), "-l", str(list_path)],
            capture_output=True, text=True, check=True,
        )
        dist_out = subprocess.run(
            ["mash", "dist", f"{sketch_prefix}.msh", f"{sketch_prefix}.msh"],
            capture_output=True, text=True, check=True,
        ).stdout

    path_to_gid = {str(p): gid for gid, p in zip(genome_ids, fasta_paths)}
    idx = {gid: i for i, gid in enumerate(genome_ids)}
    n = len(genome_ids)
    dist_sq = np.zeros((n, n), dtype=float)
    for line in dist_out.splitlines():
        ref, query, dist, _, _ = line.split("\t")
        i, j = idx[path_to_gid[ref]], idx[path_to_gid[query]]
        dist_sq[i, j] = float(dist)
    dist_sq = (dist_sq + dist_sq.T) / 2.0
    np.fill_diagonal(dist_sq, 0.0)
    return squareform(dist_sq, checks=False)


def _feature_distance_matrix(features: pd.DataFrame) -> np.ndarray:
    condensed = pdist(features.values.astype(bool), metric="jaccard")
    if np.isnan(condensed).any():
        raise ValueError(
            "NaN in feature Jaccard distance -- likely a genome with zero AMR "
            "features detected (0/0 in the Jaccard ratio). Fix by excluding "
            "all-zero rows explicitly rather than clustering through the NaN."
        )
    return condensed


def compute_distance_matrix(genome_ids: list[str], features: pd.DataFrame):
    """Return (condensed_distances, method_name, dedup_threshold, cluster_threshold)."""
    condensed = _mash_distance_matrix(genome_ids)
    if condensed is not None:
        return condensed, "mash", MASH_DEDUP_THRESHOLD, MASH_CLUSTER_THRESHOLD
    print("distance method: Jaccard over data/processed/features.parquet (mash "
          "unavailable). This only catches genomes with identical detected gene "
          "content -- weaker than true ANI, so treat cluster boundaries as "
          "conservative, not a precise phylogenetic cut.")
    return _feature_distance_matrix(features), "feature-jaccard", FEATURE_DEDUP_THRESHOLD, FEATURE_CLUSTER_THRESHOLD


def load_mlst(genome_ids: list[str]) -> pd.Series | None:
    if not BVBRC_GENOME_PATH.exists():
        return None
    bvbrc = pd.read_csv(BVBRC_GENOME_PATH, dtype=str)
    return bvbrc.drop_duplicates("Genome ID").set_index("Genome ID")["MLST"].reindex(genome_ids)


def crosscheck_mlst(cluster_labels: np.ndarray, genome_ids: list[str], mlst: pd.Series | None) -> None:
    if mlst is None:
        print("MLST cross-check: skipped (data/raw/BVBRC_genome.csv not found)")
        return
    df = pd.DataFrame({"cluster_id": cluster_labels, "mlst": mlst.to_numpy()}).dropna(subset=["mlst"])
    if df.empty:
        print("MLST cross-check: skipped (no genome in this set has an MLST call)")
        return
    mixed = df.groupby("cluster_id")["mlst"].nunique()
    fragmented = df.groupby("mlst")["cluster_id"].nunique()
    n_mixed, n_clusters_typed = int((mixed > 1).sum()), len(mixed)
    n_fragmented, n_types_typed = int((fragmented > 1).sum()), len(fragmented)
    print(f"MLST cross-check: {n_mixed}/{n_clusters_typed} typed clusters contain "
          f">1 MLST type (possible under-clustering); {n_fragmented}/{n_types_typed} "
          f"MLST types are split across >1 cluster (possible over-fragmentation)")


def assign_splits(cluster_labels: np.ndarray, min_heldout: int = MIN_HELDOUT_CLUSTERS):
    """Greedy largest-cluster-first assignment: each cluster goes to whichever split
    is furthest below its target share of genomes. Whole clusters only -- this never
    splits a cluster to fix label balance, per the hard invariant in DATA_SPEC #4.
    The smallest `min_heldout` clusters are excluded from train entirely so the
    pipeline is forced to report performance on genuinely unseen genetic groups.
    """
    sizes = pd.Series(cluster_labels).value_counts()  # cluster_id -> genome count
    n_total = int(sizes.sum())
    targets = {split: frac * n_total for split, frac in TARGET_SPLIT_FRACTIONS.items()}
    current = {"train": 0, "cal": 0, "test": 0}

    n_heldout = min(min_heldout, max(0, len(sizes) - 3))
    heldout_cluster_ids = set(sizes.sort_values(ascending=True).index[:n_heldout])

    assignment = {}
    for cluster_id, size in sizes.sort_values(ascending=False).items():
        allowed = ["cal", "test"] if cluster_id in heldout_cluster_ids else ["train", "cal", "test"]
        best = min(allowed, key=lambda s: current[s] / targets[s] if targets[s] else float("inf"))
        assignment[cluster_id] = best
        current[best] += size
    return assignment, heldout_cluster_ids, current, targets


def assert_no_cluster_spans_splits(splits: dict) -> None:
    cluster_to_splits: dict[int, set[str]] = {}
    for info in splits.values():
        cluster_to_splits.setdefault(info["cluster_id"], set()).add(info["split"])
    bad = {cid: s for cid, s in cluster_to_splits.items() if len(s) > 1}
    assert not bad, f"leakage: cluster(s) spanning multiple splits: {bad}"


def label_balance_report(splits: dict) -> pd.DataFrame:
    labels = pd.read_csv(LABELS_PATH, dtype={"genome_id": str})
    labels = labels[labels["genome_id"].isin(splits)]
    labels["split"] = labels["genome_id"].map(lambda g: splits[g]["split"])
    return labels.groupby(["antibiotic", "split", "label"]).size().unstack(fill_value=0)


def run(cluster_threshold: float | None = None, min_heldout: int = MIN_HELDOUT_CLUSTERS) -> None:
    features = pd.read_parquet(FEATURES_PATH)
    genome_ids = list(features.index)

    condensed, method, dedup_threshold, default_cluster_threshold = compute_distance_matrix(genome_ids, features)
    cluster_threshold = default_cluster_threshold if cluster_threshold is None else cluster_threshold

    Z = linkage(condensed, method="average")
    dedup_labels = fcluster(Z, t=dedup_threshold, criterion="distance")
    cluster_labels = fcluster(Z, t=cluster_threshold, criterion="distance")

    n_dedup_groups = len(set(dedup_labels))
    n_collapsed = len(genome_ids) - n_dedup_groups
    n_clusters = len(set(cluster_labels))

    mlst = load_mlst(genome_ids)
    assignment, heldout_cluster_ids, current, targets = assign_splits(cluster_labels, min_heldout)

    splits = {
        gid: {"split": assignment[cid], "cluster_id": int(cid)}
        for gid, cid in zip(genome_ids, cluster_labels)
    }
    assert_no_cluster_spans_splits(splits)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SPLITS_PATH.write_text(json.dumps(splits, indent=2, sort_keys=True))

    print("=" * 70)
    print("SPLIT SUMMARY -- paste into docs/DECISIONS.md")
    print("=" * 70)
    print(f"distance method: {method}")
    print(f"dedup threshold: {dedup_threshold}  |  cluster threshold: {cluster_threshold}")
    print(f"genomes: {len(genome_ids)} -> {n_dedup_groups} unique dedup groups "
          f"({n_collapsed} genomes collapsed as near-/exact-duplicates)")
    print(f"genetic clusters: {n_clusters}  |  held out entirely from train: {len(heldout_cluster_ids)}")
    for split_name in ("train", "cal", "test"):
        n_genomes_split = sum(1 for v in splits.values() if v["split"] == split_name)
        n_clusters_split = len({v["cluster_id"] for v in splits.values() if v["split"] == split_name})
        print(f"  {split_name}: {n_genomes_split} genomes "
              f"({n_genomes_split / len(genome_ids):.1%}, target "
              f"{TARGET_SPLIT_FRACTIONS[split_name]:.0%}), {n_clusters_split} clusters")
    crosscheck_mlst(cluster_labels, genome_ids, mlst)
    print("per-antibiotic label balance by split:")
    print(label_balance_report(splits).to_string())
    print(f"wrote {SPLITS_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster-threshold", type=float, default=None,
                         help="override the coarse clustering distance threshold "
                              "(mash default 0.002, feature-jaccard default 0.05)")
    parser.add_argument("--min-heldout-clusters", type=int, default=MIN_HELDOUT_CLUSTERS,
                         help="smallest N clusters to force entirely out of train")
    args = parser.parse_args()
    run(cluster_threshold=args.cluster_threshold, min_heldout=args.min_heldout_clusters)
