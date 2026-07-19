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
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.spatial.distance import pdist, squareform

REPO_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = REPO_ROOT / "data" / "raw"
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
FEATURES_PATH = PROCESSED_DIR / "features.parquet"
LABELS_PATH = PROCESSED_DIR / "labels.csv"
BVBRC_GENOME_PATH = RAW_DIR / "BVBRC_genome.csv"
SPLITS_PATH = PROCESSED_DIR / "splits.json"
SPLIT_AUDIT_PATH = PROCESSED_DIR / "split_audit.json"

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


def _cluster_label_summary(cluster_labels: np.ndarray, genome_ids: list[str]) -> pd.DataFrame:
    labels = pd.read_csv(LABELS_PATH, dtype={"genome_id": str})
    labels = labels[labels["genome_id"].isin(genome_ids)].copy()
    labels["stratum"] = labels["antibiotic"] + "__" + labels["label"]
    strata = pd.crosstab(labels["genome_id"], labels["stratum"]).reindex(genome_ids, fill_value=0)
    strata["genome_count"] = 1
    strata["cluster_id"] = cluster_labels
    return strata.groupby("cluster_id").sum()


def assign_splits(
    cluster_labels: np.ndarray,
    genome_ids: list[str],
    min_heldout: int = MIN_HELDOUT_CLUSTERS,
):
    """Assign whole clusters with a small mixed-integer stratification problem.

    The objective minimizes normalized absolute deviation from the requested genome
    and per-antibiotic R/S counts.  Genome counts receive extra weight and a hard
    tolerance.  This avoids a size-perfect split whose calibration partition contains
    too few examples of a clinically important class.  No individual genome is moved
    outside its Mash/ANI cluster to improve balance.
    """
    summary = _cluster_label_summary(cluster_labels, genome_ids)
    cluster_ids = list(summary.index)
    split_names = list(TARGET_SPLIT_FRACTIONS)
    fractions = np.array([TARGET_SPLIT_FRACTIONS[name] for name in split_names])
    dimensions = list(summary.columns)
    n_clusters = len(cluster_ids)
    n_splits = len(split_names)
    n_dimensions = len(dimensions)
    n_assignment = n_clusters * n_splits
    n_variables = n_assignment + n_splits * n_dimensions

    objective = np.zeros(n_variables)
    for split_index, fraction in enumerate(fractions):
        for dimension_index, dimension in enumerate(dimensions):
            target = float(summary[dimension].sum() * fraction)
            weight = 12.0 if dimension == "genome_count" else 1.0
            objective[n_assignment + split_index * n_dimensions + dimension_index] = (
                weight / max(target, 1.0)
            )

    rows: list[np.ndarray] = []
    lower: list[float] = []
    upper: list[float] = []
    for cluster_index in range(n_clusters):
        row = np.zeros(n_variables)
        row[cluster_index * n_splits : (cluster_index + 1) * n_splits] = 1
        rows.append(row)
        lower.append(1)
        upper.append(1)

    size_tolerance = max(5, round(0.012 * len(genome_ids)))
    for split_index, fraction in enumerate(fractions):
        assignment_indices = np.arange(n_clusters) * n_splits + split_index
        for dimension_index, dimension in enumerate(dimensions):
            values = summary[dimension].to_numpy(dtype=float)
            target = float(values.sum() * fraction)
            deviation_index = n_assignment + split_index * n_dimensions + dimension_index

            # assignment total - deviation <= target
            row = np.zeros(n_variables)
            row[assignment_indices] = values
            row[deviation_index] = -1
            rows.append(row)
            lower.append(-np.inf)
            upper.append(target)

            # -assignment total - deviation <= -target
            row = np.zeros(n_variables)
            row[assignment_indices] = -values
            row[deviation_index] = -1
            rows.append(row)
            lower.append(-np.inf)
            upper.append(-target)

            hard_bound = np.zeros(n_variables)
            hard_bound[assignment_indices] = values
            rows.append(hard_bound)
            if dimension == "genome_count":
                lower.append(target - size_tolerance)
                upper.append(target + size_tolerance)
            else:
                # A broad floor prevents nearly empty R/S calibration strata while
                # leaving the optimizer freedom to respect indivisible clusters.
                lower.append(min(target, max(2.0, 0.45 * target)))
                upper.append(np.inf)

    n_heldout = min(min_heldout, max(0, n_clusters - n_splits))
    heldout_cluster_ids = set(summary["genome_count"].nsmallest(n_heldout).index)
    for cluster_id in heldout_cluster_ids:
        row = np.zeros(n_variables)
        row[cluster_ids.index(cluster_id) * n_splits + split_names.index("train")] = 1
        rows.append(row)
        lower.append(0)
        upper.append(0)

    result = milp(
        objective,
        integrality=np.r_[np.ones(n_assignment), np.zeros(n_variables - n_assignment)],
        bounds=Bounds(
            np.zeros(n_variables),
            np.r_[np.ones(n_assignment), np.full(n_variables - n_assignment, np.inf)],
        ),
        constraints=LinearConstraint(np.array(rows), np.array(lower), np.array(upper)),
        options={"time_limit": 60},
    )
    if not result.success:
        raise RuntimeError(f"could not construct a label-balanced grouped split: {result.message}")

    matrix = result.x[:n_assignment].reshape(n_clusters, n_splits)
    assignment = {
        cluster_id: split_names[int(np.argmax(matrix[index]))]
        for index, cluster_id in enumerate(cluster_ids)
    }
    current = {
        split: int(
            summary.loc[[cid for cid in cluster_ids if assignment[cid] == split], "genome_count"].sum()
        )
        for split in split_names
    }
    targets = {
        split: float(TARGET_SPLIT_FRACTIONS[split] * len(genome_ids)) for split in split_names
    }
    return assignment, heldout_cluster_ids, current, targets


def assert_no_cluster_spans_splits(splits: dict) -> None:
    cluster_to_splits: dict[int, set[str]] = {}
    for info in splits.values():
        cluster_to_splits.setdefault(info["cluster_id"], set()).add(info["split"])
    bad = {cid: s for cid, s in cluster_to_splits.items() if len(s) > 1}
    assert not bad, f"leakage: cluster(s) spanning multiple splits: {bad}"


def assert_no_dedup_group_spans_splits(splits: dict) -> None:
    """A stricter invariant for the near-identical-genome groups."""
    dedup_to_splits: dict[int, set[str]] = {}
    for info in splits.values():
        dedup_to_splits.setdefault(info["dedup_group_id"], set()).add(info["split"])
    bad = {gid: values for gid, values in dedup_to_splits.items() if len(values) > 1}
    assert not bad, f"leakage: dedup group(s) spanning multiple splits: {bad}"


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
    assignment, heldout_cluster_ids, current, targets = assign_splits(
        cluster_labels, genome_ids, min_heldout
    )

    dedup_sizes = pd.Series(dedup_labels).value_counts().to_dict()
    splits = {
        gid: {
            "split": assignment[cid],
            "cluster_id": int(cid),
            "dedup_group_id": int(did),
            "dedup_group_size": int(dedup_sizes[did]),
        }
        for gid, cid, did in zip(genome_ids, cluster_labels, dedup_labels)
    }
    assert_no_cluster_spans_splits(splits)
    assert_no_dedup_group_spans_splits(splits)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    SPLITS_PATH.write_text(json.dumps(splits, indent=2, sort_keys=True))
    audit = {
        "distance_method": method,
        "dedup_threshold": dedup_threshold,
        "cluster_threshold": cluster_threshold,
        "n_genomes_retained": len(genome_ids),
        "n_dedup_groups": n_dedup_groups,
        "n_rows_in_excess_of_one_per_dedup_group": n_collapsed,
        "n_clusters": n_clusters,
        "assignment_method": "mixed-integer whole-cluster label stratification",
        "split_counts": current,
        "target_counts": targets,
        "heldout_cluster_ids": sorted(int(x) for x in heldout_cluster_ids),
        "all_rows_retained": True,
        "recommended_training_weight": "1 / labeled genomes in dedup_group_id",
    }
    SPLIT_AUDIT_PATH.write_text(json.dumps(audit, indent=2, sort_keys=True))

    print("=" * 70)
    print("SPLIT SUMMARY -- paste into docs/DECISIONS.md")
    print("=" * 70)
    print(f"distance method: {method}")
    print(f"dedup threshold: {dedup_threshold}  |  cluster threshold: {cluster_threshold}")
    print(f"genomes retained: {len(genome_ids)}; {n_dedup_groups} unique dedup groups "
          f"({n_collapsed} rows beyond one representative; no rows deleted)")
    print(f"genetic clusters: {n_clusters}  |  held out entirely from train: {len(heldout_cluster_ids)}")
    print("assignment method: mixed-integer whole-cluster R/S stratification")
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
    print(f"wrote {SPLIT_AUDIT_PATH}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cluster-threshold", type=float, default=None,
                         help="override the coarse clustering distance threshold "
                              "(mash default 0.002, feature-jaccard default 0.05)")
    parser.add_argument("--min-heldout-clusters", type=int, default=MIN_HELDOUT_CLUSTERS,
                         help="smallest N clusters to force entirely out of train")
    args = parser.parse_args()
    run(cluster_threshold=args.cluster_threshold, min_heldout=args.min_heldout_clusters)
