"""Fit deployable genotype-only XGBoost models on every labeled genome.

The honest model estimate remains the previously frozen Mash-separated test
report in ``reports/soft_ensemble``. This command is a deployment refit only:
for each antibiotic it tunes XGBoost and learns sigmoid calibration from grouped
out-of-fold predictions over all labeled rows, then refits XGBoost on all rows.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import sklearn

from genome_firewall.ensemble_calibration import ScoreCalibrator
from genome_firewall.model_ensemble import (
    DEFAULT_FEATURES,
    DEFAULT_LABELS,
    DEFAULT_SPLITS,
    _normalise_weight,
    build_model,
    compute_metrics,
    duplicate_weights,
    load_feature_setups,
    load_metadata,
    tune_model,
)
from genome_firewall.serving import CalibratedClassifier


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT = ROOT / "data" / "processed" / "final_models"
MODEL_NAME = "xgboost"
MODEL_VERSION = "bioshield-xgboost-v1"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def train(args: argparse.Namespace) -> dict:
    features_path = Path(args.features).resolve()
    labels_path = Path(args.labels).resolve()
    splits_path = Path(args.splits).resolve()
    output_dir = Path(args.output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    setup = load_feature_setups(features_path)["genotype_only"]
    labels, metadata = load_metadata(setup.frame, labels_path, splits_path)
    antibiotics = args.antibiotics or sorted(labels["antibiotic"].unique())
    feature_spec = json.loads((features_path.parent / "feature_spec.json").read_text())

    manifest: dict = {
        "model_version": MODEL_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "purpose": "deployment refit on all labeled data; not an evaluation",
        "model": MODEL_NAME,
        "calibration": "sigmoid from grouped out-of-fold XGBoost predictions",
        "decision_threshold": 0.5,
        "no_call_band": [args.no_call_low, args.no_call_high],
        "duplicate_weighting": "inverse labeled dedup-group size",
        "cv_folds": args.cv_folds,
        "seed": args.seed,
        "feature_count": len(setup.frame.columns),
        "feature_spec_version": feature_spec.get("version"),
        "amrfinder_db_version": feature_spec.get("amrfinder_db_version"),
        "data": {
            "features_sha256": _sha256(features_path),
            "labels_sha256": _sha256(labels_path),
            "splits_sha256": _sha256(splits_path),
        },
        "versions": {
            "python": sys.version.split()[0],
            "scikit_learn": sklearn.__version__,
            "xgboost": __import__("xgboost").__version__,
        },
        "antibiotics": {},
    }

    for antibiotic in antibiotics:
        antibiotic_labels = labels[labels["antibiotic"] == antibiotic].set_index("genome_id")
        ids = antibiotic_labels.index.intersection(metadata.index, sort=False)
        X = setup.frame.loc[ids]
        y = (antibiotic_labels.loc[ids, "label"] == "R").astype(int).to_numpy()
        meta = metadata.loc[ids]
        groups = meta["cluster_id"].to_numpy()
        weight = duplicate_weights(meta["dedup_group_id"])

        if len(np.unique(y)) != 2:
            raise ValueError(f"{antibiotic} does not contain both R and S labels")

        params, oof_probability, oof_brier = tune_model(
            MODEL_NAME, setup, X, y, groups, weight,
            args.cv_folds, args.seed, args.quick,
        )
        calibrator = ScoreCalibrator("sigmoid").fit(
            oof_probability, y, _normalise_weight(weight)
        )
        calibrated_oof = calibrator.predict(oof_probability)
        metrics = compute_metrics(
            y, calibrated_oof, weight, args.no_call_low, args.no_call_high
        )
        fitted = build_model(MODEL_NAME, params, setup, y, args.seed)
        fitted.fit(X, y, model__sample_weight=_normalise_weight(weight))
        model = CalibratedClassifier(
            estimator=fitted,
            feature_columns=list(setup.frame.columns),
            calibrator=calibrator,
        )
        artifact_path = output_dir / f"{antibiotic}.pkl"
        with artifact_path.open("wb") as handle:
            pickle.dump(model, handle, protocol=pickle.HIGHEST_PROTOCOL)

        manifest["antibiotics"][antibiotic] = {
            "n_labeled": int(len(y)),
            "n_resistant": int(y.sum()),
            "n_susceptible": int((1 - y).sum()),
            "n_clusters": int(pd.Series(groups).nunique()),
            "parameters": params,
            "xgboost_oof_weighted_brier_before_calibration": oof_brier,
            "grouped_oof_diagnostics": metrics,
            "artifact": artifact_path.name,
        }
        print(
            f"fitted {antibiotic:15s} n={len(y):4d} "
            f"OOF weighted Brier={metrics['weighted_brier']:.4f}"
        )

    manifest_path = Path(args.manifest).resolve() if args.manifest else output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"wrote {len(antibiotics)} final models to {output_dir}")
    print(f"wrote manifest to {manifest_path}")
    return manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", default=str(DEFAULT_FEATURES))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--splits", default=str(DEFAULT_SPLITS))
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--manifest", default=None)
    parser.add_argument("--antibiotics", nargs="+", default=None)
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--no-call-low", type=float, default=0.4)
    parser.add_argument("--no-call-high", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quick", action="store_true")
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not 0 <= args.no_call_low < args.no_call_high <= 1:
        raise ValueError("no-call band must satisfy 0 <= low < high <= 1")
    train(args)


if __name__ == "__main__":
    main()
