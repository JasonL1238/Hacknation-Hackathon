"""Read-only validation for the focused local model bakeoff."""

from __future__ import annotations

import importlib.util
import inspect
import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
FEATURES = REPO_ROOT / "data" / "processed" / "features.parquet"
LABELS = REPO_ROOT / "data" / "processed" / "labels.csv"
SPLITS = REPO_ROOT / "data" / "processed" / "splits.json"
DRUGS = REPO_ROOT / "db" / "drugs_saureus.csv"
REGISTRY = Path(__file__).with_name("registry.json")


def module_available(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except ModuleNotFoundError:
        return False


def supports_sample_weight(module_name: str, class_name: str) -> str:
    if not module_available(module_name):
        return "not installed"
    module = __import__(module_name, fromlist=[class_name])
    estimator = getattr(module, class_name)
    parameters = inspect.signature(estimator.fit).parameters
    return "yes" if "sample_weight" in parameters else "no"


def main() -> None:
    required = (FEATURES, LABELS, SPLITS, DRUGS, REGISTRY)
    missing = [str(path.relative_to(REPO_ROOT)) for path in required if not path.exists()]
    if missing:
        raise SystemExit(f"missing required bakeoff files: {missing}")

    features = pd.read_parquet(FEATURES)
    if "genome_id" in features.columns:
        features = features.set_index("genome_id")
    features.index = features.index.astype(str)
    if not features.index.is_unique or features.isna().any().any():
        raise SystemExit("features require a unique genome_id index and no missing values")

    labels = pd.read_csv(LABELS, dtype={"genome_id": str})
    split_records = json.loads(SPLITS.read_text())
    metadata = pd.DataFrame.from_dict(split_records, orient="index")
    metadata.index = metadata.index.astype(str)
    required_split_fields = {"split", "cluster_id", "dedup_group_id", "dedup_group_size"}
    if missing_fields := required_split_fields.difference(metadata.columns):
        raise SystemExit(f"splits.json missing fields: {sorted(missing_fields)}")

    missing_metadata = features.index.difference(metadata.index)
    if len(missing_metadata):
        raise SystemExit(f"splits.json missing {len(missing_metadata)} feature genomes")
    for field in ("cluster_id", "dedup_group_id"):
        leakage = metadata.groupby(field)["split"].nunique()
        if (leakage > 1).any():
            raise SystemExit(f"{field} spans train/cal/test")

    print("Focused bakeoff data check: PASS")
    print(
        f"genomes={len(features)} features={features.shape[1]} "
        f"dedup_families={metadata['dedup_group_id'].nunique()} "
        f"mash_clusters={metadata['cluster_id'].nunique()}"
    )
    print("\nEffective labeled training size:")
    print(f"{'antibiotic':18s} {'rows':>6s} {'dedup families':>15s} {'clusters':>9s}")
    for antibiotic, rows in labels.groupby("antibiotic"):
        ids = pd.Index(rows["genome_id"]).intersection(metadata.index)
        train = metadata.loc[ids]
        train = train[train["split"] == "train"]
        print(
            f"{antibiotic:18s} {len(train):6d} "
            f"{train['dedup_group_id'].nunique():15d} {train['cluster_id'].nunique():9d}"
        )

    print("\nLocal dependencies:")
    for name in ("sklearn", "xgboost", "interpret", "tabpfn", "torch"):
        print(f"{name:12s} {'installed' if module_available(name) else 'missing'}")
    print(
        "EBM sample_weight:",
        supports_sample_weight("interpret.glassbox", "ExplainableBoostingClassifier"),
    )
    print(
        "TabPFN sample_weight:",
        supports_sample_weight("tabpfn", "TabPFNClassifier"),
    )

    registry = json.loads(REGISTRY.read_text())
    print("\nRegistry:")
    for model in registry["models"]:
        print(f"{model['name']:30s} {model['status']}")


if __name__ == "__main__":
    main()
