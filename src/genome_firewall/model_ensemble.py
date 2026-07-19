"""Duplicate-aware soft-voting training for Genome Firewall.

The module trains one classifier per antibiotic and feature setup.  Its three base
learners are L1 logistic regression, HistGradientBoosting, and XGBoost; their
probabilities are averaged and the final average is calibrated on the dedicated
calibration split.  Hyperparameters are selected only with grouped cross-validation
inside the training split.

All genome rows are retained.  Near-identical genomes receive inverse dedup-group
weights, so a repeated family contributes approximately one vote without pretending
that genomes sharing an AMR feature profile are biologically interchangeable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    f1_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED_DIR = REPO_ROOT / "data" / "processed"
DEFAULT_FEATURES = PROCESSED_DIR / "features.parquet"
DEFAULT_LABELS = PROCESSED_DIR / "labels.csv"
DEFAULT_SPLITS = PROCESSED_DIR / "splits.json"
DEFAULT_DRUGS = REPO_ROOT / "db" / "drugs_saureus.csv"
DEFAULT_REPORT_DIR = REPO_ROOT / "reports" / "soft_ensemble"
DEFAULT_ARTIFACT_DIR = PROCESSED_DIR / "ensemble_models"

EMBEDDING_CANDIDATES = {
    "esm2": [
        PROCESSED_DIR / "esm2_embeddings.parquet",
        REPO_ROOT / "data" / "interim" / "esm2_embeddings.parquet",
    ],
    "dnabert2": [
        PROCESSED_DIR / "dnabert2_embeddings.parquet",
        REPO_ROOT / "data" / "interim" / "dnabert2_embeddings.parquet",
    ],
}

BASE_MODELS = ("l1_logistic", "hist_gradient_boosting", "xgboost")


@dataclass(frozen=True)
class FeatureSetup:
    name: str
    frame: pd.DataFrame
    genotype_columns: tuple[str, ...]
    embedding_columns: tuple[str, ...]


class ScoreCalibrator:
    """A small serializable calibrator fitted to one-dimensional model scores."""

    def __init__(self, method: str = "sigmoid") -> None:
        if method not in {"sigmoid", "isotonic"}:
            raise ValueError("calibration must be 'sigmoid' or 'isotonic'")
        self.method = method
        self.model: Any | None = None

    @staticmethod
    def _logit(probability: np.ndarray) -> np.ndarray:
        p = np.clip(np.asarray(probability, dtype=float), 1e-6, 1 - 1e-6)
        return np.log(p / (1 - p)).reshape(-1, 1)

    def fit(
        self, probability: np.ndarray, y: np.ndarray, sample_weight: np.ndarray
    ) -> "ScoreCalibrator":
        if len(np.unique(y)) < 2:
            raise ValueError("calibration split must contain both R and S labels")
        if self.method == "sigmoid":
            self.model = LogisticRegression(C=1e6, solver="lbfgs", max_iter=2000)
            self.model.fit(self._logit(probability), y, sample_weight=sample_weight)
        else:
            self.model = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
            self.model.fit(probability, y, sample_weight=sample_weight)
        return self

    def predict(self, probability: np.ndarray) -> np.ndarray:
        if self.model is None:
            raise RuntimeError("calibrator has not been fitted")
        if self.method == "sigmoid":
            return self.model.predict_proba(self._logit(probability))[:, 1]
        return np.asarray(self.model.predict(probability), dtype=float)


def _read_indexed_parquet(path: Path, prefix: str) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    if "genome_id" in frame.columns:
        frame = frame.set_index("genome_id")
    frame.index = frame.index.astype(str)
    frame.index.name = "genome_id"
    if not frame.index.is_unique:
        duplicates = frame.index[frame.index.duplicated()].unique()[:5].tolist()
        raise ValueError(f"{path} has duplicate genome_id values, e.g. {duplicates}")
    non_numeric = frame.select_dtypes(exclude=[np.number]).columns.tolist()
    if non_numeric:
        raise ValueError(f"{path} has non-numeric embedding columns: {non_numeric[:5]}")
    values = frame.to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValueError(f"{path} contains NaN or infinite embedding values")
    frame = frame.astype("float32")
    frame.columns = [f"{prefix}__{column}" for column in frame.columns]
    return frame.sort_index()


def _discover_embedding(explicit: str | None, kind: str) -> Path | None:
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not path.exists():
            raise FileNotFoundError(f"requested {kind} embeddings not found: {path}")
        return path
    return next((path for path in EMBEDDING_CANDIDATES[kind] if path.exists()), None)


def load_feature_setups(
    features_path: Path,
    esm2_path: Path | None = None,
    dnabert2_path: Path | None = None,
    include_combined: bool = False,
) -> dict[str, FeatureSetup]:
    genotype = pd.read_parquet(features_path)
    if "genome_id" in genotype.columns:
        genotype = genotype.set_index("genome_id")
    genotype.index = genotype.index.astype(str)
    genotype.index.name = "genome_id"
    if not genotype.index.is_unique or genotype.isna().any().any():
        raise ValueError("genotype features require a unique genome_id index and no missing values")
    genotype = genotype.astype("float32").sort_index()
    genotype.columns = [f"geno__{column}" for column in genotype.columns]
    genotype_columns = tuple(genotype.columns)

    setups: dict[str, FeatureSetup] = {
        "genotype_only": FeatureSetup(
            "genotype_only", genotype, genotype_columns, tuple()
        )
    }
    embeddings: dict[str, pd.DataFrame] = {}
    for kind, path in (("esm2", esm2_path), ("dnabert2", dnabert2_path)):
        if path is None:
            continue
        embedded = _read_indexed_parquet(path, kind)
        missing = genotype.index.difference(embedded.index)
        if len(missing):
            raise ValueError(
                f"{kind} embeddings are missing {len(missing)} genotype genomes "
                f"(e.g. {missing[:5].tolist()}); regenerate a complete cache"
            )
        embedded = embedded.reindex(genotype.index)
        embeddings[kind] = embedded
        embedding_columns = tuple(embedded.columns)
        setups[f"{kind}_only"] = FeatureSetup(
            f"{kind}_only", embedded, tuple(), embedding_columns
        )
        concatenated = pd.concat([genotype, embedded], axis=1)
        setups[f"genotype_plus_{kind}"] = FeatureSetup(
            f"genotype_plus_{kind}",
            concatenated,
            genotype_columns,
            embedding_columns,
        )

    if include_combined and {"esm2", "dnabert2"}.issubset(embeddings):
        combined = pd.concat([genotype, embeddings["esm2"], embeddings["dnabert2"]], axis=1)
        embedding_columns = tuple(embeddings["esm2"].columns) + tuple(
            embeddings["dnabert2"].columns
        )
        setups["genotype_plus_esm2_plus_dnabert2"] = FeatureSetup(
            "genotype_plus_esm2_plus_dnabert2",
            combined,
            genotype_columns,
            embedding_columns,
        )
    return setups


def _exact_profile_groups(genotype: pd.DataFrame) -> pd.Series:
    """Stable exact-profile IDs for old split files without dedup_group_id."""
    binary = genotype.to_numpy(dtype=np.uint8)
    packed = np.packbits(binary, axis=1)
    values = [hashlib.sha256(row.tobytes()).hexdigest()[:16] for row in packed]
    return pd.Series(values, index=genotype.index, name="dedup_group_id")


def load_metadata(
    genotype: pd.DataFrame, labels_path: Path, splits_path: Path
) -> tuple[pd.DataFrame, pd.DataFrame]:
    labels = pd.read_csv(labels_path, dtype={"genome_id": str})
    required = {"genome_id", "antibiotic", "label"}
    if not required.issubset(labels.columns):
        raise ValueError(f"labels missing required columns: {sorted(required - set(labels.columns))}")
    if labels.duplicated(["genome_id", "antibiotic"]).any():
        raise ValueError("labels contain duplicate (genome_id, antibiotic) rows")
    if not set(labels["label"]).issubset({"R", "S"}):
        raise ValueError("labels must contain only R and S")

    raw_splits = json.loads(splits_path.read_text())
    metadata = pd.DataFrame.from_dict(raw_splits, orient="index")
    metadata.index = metadata.index.astype(str)
    metadata.index.name = "genome_id"
    missing = genotype.index.difference(metadata.index)
    if len(missing):
        raise ValueError(f"splits.json is missing {len(missing)} feature genomes")
    metadata = metadata.reindex(genotype.index)
    if not set(metadata["split"]).issubset({"train", "cal", "test"}):
        raise ValueError("invalid split name in splits.json")
    leakage = metadata.groupby("cluster_id")["split"].nunique()
    if (leakage > 1).any():
        raise ValueError("cluster_id spans train/cal/test; refusing to train")

    if "dedup_group_id" not in metadata:
        warnings.warn(
            "splits.json has no dedup_group_id; deriving exact AMR-feature profile "
            "groups. Re-run `make split` with Mash installed for the stronger genome audit.",
            stacklevel=2,
        )
        metadata["dedup_group_id"] = _exact_profile_groups(genotype)
    dedup_leakage = metadata.groupby("dedup_group_id")["split"].nunique()
    if (dedup_leakage > 1).any():
        raise ValueError("dedup_group_id spans train/cal/test; refusing to train")
    return labels, metadata


def duplicate_weights(dedup_group: pd.Series) -> np.ndarray:
    """Give all labeled members of a duplicate family a combined weight of one."""
    counts = dedup_group.value_counts()
    return dedup_group.map(lambda value: 1.0 / counts[value]).to_numpy(dtype=float)


def _normalise_weight(weight: np.ndarray) -> np.ndarray:
    return weight / np.mean(weight)


def _parameter_grid(model_name: str, quick: bool) -> list[dict[str, Any]]:
    grids = {
        "l1_logistic": [
            {"C": value} for value in ([0.1, 1.0] if quick else [0.01, 0.1, 1.0, 10.0])
        ],
        "hist_gradient_boosting": [
            {"learning_rate": 0.05, "max_leaf_nodes": 7, "l2_regularization": 1.0},
            {"learning_rate": 0.05, "max_leaf_nodes": 15, "l2_regularization": 3.0},
        ],
        "xgboost": [
            {"learning_rate": 0.05, "max_depth": 2, "min_child_weight": 3.0},
            {"learning_rate": 0.05, "max_depth": 3, "min_child_weight": 5.0},
        ],
    }
    return grids[model_name][:1] if quick else grids[model_name]


def _preprocessor(setup: FeatureSetup) -> ColumnTransformer:
    transformers: list[tuple[str, Any, list[str]]] = []
    if setup.genotype_columns:
        transformers.append(
            (
                "genotype",
                Pipeline(
                    [("impute", SimpleImputer(strategy="constant", fill_value=0)), ("scale", StandardScaler())]
                ),
                list(setup.genotype_columns),
            )
        )
    if setup.embedding_columns:
        transformers.append(
            (
                "embedding",
                Pipeline(
                    [("impute", SimpleImputer(strategy="median")), ("scale", StandardScaler())]
                ),
                list(setup.embedding_columns),
            )
        )
    return ColumnTransformer(transformers, remainder="drop")


def build_model(
    model_name: str,
    params: dict[str, Any],
    setup: FeatureSetup,
    y: np.ndarray,
    seed: int,
) -> Pipeline:
    if model_name == "l1_logistic":
        estimator: BaseEstimator = LogisticRegression(
            l1_ratio=1.0,
            solver="liblinear",
            class_weight="balanced",
            max_iter=3000,
            random_state=seed,
            **params,
        )
        return Pipeline([("preprocess", _preprocessor(setup)), ("model", estimator)])
    if model_name == "hist_gradient_boosting":
        estimator = HistGradientBoostingClassifier(
            max_iter=250,
            class_weight="balanced",
            early_stopping=False,
            random_state=seed,
            **params,
        )
        return Pipeline([("model", estimator)])
    if model_name == "xgboost":
        try:
            from xgboost import XGBClassifier
        except ImportError as exc:
            raise RuntimeError(
                "XGBoost is required for the three-model ensemble. Install the project "
                "environment or run `pip install xgboost`."
            ) from exc
        negatives = max(1, int((y == 0).sum()))
        positives = max(1, int((y == 1).sum()))
        estimator = XGBClassifier(
            n_estimators=300,
            objective="binary:logistic",
            eval_metric="logloss",
            tree_method="hist",
            subsample=0.8,
            colsample_bytree=0.8,
            reg_alpha=0.1,
            reg_lambda=3.0,
            scale_pos_weight=negatives / positives,
            random_state=seed,
            n_jobs=1,
            **params,
        )
        return Pipeline([("model", estimator)])
    raise ValueError(f"unknown model: {model_name}")


def _grouped_folds(
    X: pd.DataFrame, y: np.ndarray, groups: np.ndarray, n_splits: int, seed: int
) -> list[tuple[np.ndarray, np.ndarray]]:
    n_splits = min(n_splits, len(np.unique(groups)))
    if n_splits < 2:
        raise ValueError("at least two training clusters are required")
    while n_splits >= 2:
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        folds = list(splitter.split(X, y, groups))
        if all(len(np.unique(y[train_idx])) == 2 for train_idx, _ in folds):
            return folds
        n_splits -= 1
    raise ValueError("could not create grouped folds with both classes in every training fold")


def tune_model(
    model_name: str,
    setup: FeatureSetup,
    X: pd.DataFrame,
    y: np.ndarray,
    groups: np.ndarray,
    weight: np.ndarray,
    cv_folds: int,
    seed: int,
    quick: bool,
) -> tuple[dict[str, Any], np.ndarray, float]:
    folds = _grouped_folds(X, y, groups, 2 if quick else cv_folds, seed)
    best_params: dict[str, Any] | None = None
    best_oof: np.ndarray | None = None
    best_score = math.inf
    for params in _parameter_grid(model_name, quick):
        oof = np.full(len(y), np.nan, dtype=float)
        for train_idx, validation_idx in folds:
            model = build_model(model_name, params, setup, y[train_idx], seed)
            model.fit(
                X.iloc[train_idx],
                y[train_idx],
                model__sample_weight=_normalise_weight(weight[train_idx]),
            )
            oof[validation_idx] = model.predict_proba(X.iloc[validation_idx])[:, 1]
        if np.isnan(oof).any():
            raise RuntimeError("grouped OOF prediction did not cover every training row")
        score = brier_score_loss(y, oof, sample_weight=weight)
        if score < best_score:
            best_params, best_oof, best_score = params, oof, float(score)
    assert best_params is not None and best_oof is not None
    return best_params, best_oof, best_score


def _safe_auc(y: np.ndarray, probability: np.ndarray, weight: np.ndarray, pr: bool) -> float:
    if len(np.unique(y)) < 2:
        return math.nan
    if pr:
        return float(average_precision_score(y, probability, sample_weight=weight))
    return float(roc_auc_score(y, probability, sample_weight=weight))


def compute_metrics(
    y: np.ndarray, probability: np.ndarray, weight: np.ndarray, no_call_low: float, no_call_high: float
) -> dict[str, float | int]:
    prediction = (probability >= 0.5).astype(int)
    called = (probability < no_call_low) | (probability > no_call_high)
    both_classes = len(np.unique(y)) == 2
    result: dict[str, float | int] = {
        "n": int(len(y)),
        "accuracy": float(accuracy_score(y, prediction)),
        "recall_R": float(recall_score(y, prediction, pos_label=1, zero_division=0)),
        "recall_S": float(recall_score(y, prediction, pos_label=0, zero_division=0)),
        "f1": float(f1_score(y, prediction, zero_division=0)),
        "balanced_accuracy": float(
            (
                recall_score(y, prediction, pos_label=1, zero_division=0)
                + recall_score(y, prediction, pos_label=0, zero_division=0)
            )
            / 2
        ) if both_classes else math.nan,
        "auroc": _safe_auc(y, probability, np.ones(len(y)), pr=False),
        "pr_auc": _safe_auc(y, probability, np.ones(len(y)), pr=True),
        "brier": float(brier_score_loss(y, probability)),
        "no_call_rate": float(1 - called.mean()),
        "accuracy_on_called": float(accuracy_score(y[called], prediction[called])) if called.any() else math.nan,
    }
    weighted_prediction_metrics = {
        "weighted_accuracy": accuracy_score(y, prediction, sample_weight=weight),
        "weighted_recall_R": recall_score(
            y, prediction, pos_label=1, sample_weight=weight, zero_division=0
        ),
        "weighted_recall_S": recall_score(
            y, prediction, pos_label=0, sample_weight=weight, zero_division=0
        ),
        "weighted_f1": f1_score(y, prediction, sample_weight=weight, zero_division=0),
        "weighted_balanced_accuracy": (
            recall_score(y, prediction, pos_label=1, sample_weight=weight, zero_division=0)
            + recall_score(y, prediction, pos_label=0, sample_weight=weight, zero_division=0)
        ) / 2 if both_classes else math.nan,
        "weighted_auroc": _safe_auc(y, probability, weight, pr=False),
        "weighted_pr_auc": _safe_auc(y, probability, weight, pr=True),
        "weighted_brier": brier_score_loss(y, probability, sample_weight=weight),
        "weighted_no_call_rate": np.average(~called, weights=weight),
        "weighted_accuracy_on_called": accuracy_score(
            y[called], prediction[called], sample_weight=weight[called]
        ) if called.any() else math.nan,
    }
    result.update({key: float(value) for key, value in weighted_prediction_metrics.items()})
    return result


def _pairwise_disagreement(oof: dict[str, np.ndarray]) -> list[dict[str, Any]]:
    rows = []
    names = list(oof)
    for i, left in enumerate(names):
        for right in names[i + 1 :]:
            rows.append(
                {
                    "model_a": left,
                    "model_b": right,
                    "disagreement_rate": float(
                        np.mean((oof[left] >= 0.5) != (oof[right] >= 0.5))
                    ),
                    "probability_correlation": float(np.corrcoef(oof[left], oof[right])[0, 1]),
                }
            )
    return rows


def _voting_weights(oof_brier: dict[str, float], strategy: str) -> dict[str, float]:
    if strategy == "uniform":
        return {name: 1.0 / len(oof_brier) for name in oof_brier}
    inverse = {name: 1.0 / max(score, 1e-6) for name, score in oof_brier.items()}
    total = sum(inverse.values())
    return {name: value / total for name, value in inverse.items()}


def _weighted_average(probabilities: dict[str, np.ndarray], weights: dict[str, float]) -> np.ndarray:
    return sum(probabilities[name] * weights[name] for name in weights)


def _l1_coefficient_rows(
    model: Pipeline,
    antibiotic: str,
    setup_name: str,
    known_markers: set[str],
) -> list[dict[str, Any]]:
    names = model.named_steps["preprocess"].get_feature_names_out()
    coefficients = model.named_steps["model"].coef_[0]
    rows = []
    for feature_name, coefficient in zip(names, coefficients):
        if abs(coefficient) <= 1e-12:
            continue
        # ColumnTransformer adds a transformer prefix.  Keep the source prefix
        # (geno__/esm2__/dnabert2__) because it makes the output self-describing.
        feature_name = str(feature_name).split("__", 1)[-1]
        marker_name = feature_name.split("__", 1)[-1]
        rows.append(
            {
                "antibiotic": antibiotic,
                "feature_setup": setup_name,
                "feature": feature_name,
                "coefficient": float(coefficient),
                "absolute_coefficient": float(abs(coefficient)),
                "direction": "higher_P_R" if coefficient > 0 else "lower_P_R",
                "known_catalog_marker": marker_name in known_markers,
                "interpretation": "statistical association; not proven causation",
            }
        )
    return rows


def _plot_reliability(
    predictions: pd.DataFrame, selections: pd.DataFrame, output_dir: Path
) -> None:
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        warnings.warn("matplotlib unavailable; reliability plots skipped", stacklevel=2)
        return
    for row in selections.itertuples(index=False):
        subset = predictions[
            (predictions["antibiotic"] == row.antibiotic)
            & (predictions["feature_setup"] == row.feature_setup)
            & (predictions["model"] == "soft_ensemble")
        ]
        if subset.empty:
            continue
        bins = pd.cut(subset["probability"], np.linspace(0, 1, 11), include_lowest=True)
        reliability = subset.groupby(bins, observed=False).agg(
            mean_probability=("probability", "mean"), observed_resistance=("y_true", "mean")
        ).dropna()
        fig, axis = plt.subplots(figsize=(5, 5))
        axis.plot([0, 1], [0, 1], "--", color="gray", label="ideal")
        axis.plot(
            reliability["mean_probability"], reliability["observed_resistance"], "o-", label="ensemble"
        )
        axis.set(xlabel="Predicted P(R)", ylabel="Observed resistant fraction", title=f"{row.antibiotic}: {row.feature_setup}", xlim=(0, 1), ylim=(0, 1))
        axis.legend()
        fig.tight_layout()
        fig.savefig(output_dir / f"reliability_{row.antibiotic}.png", dpi=160)
        plt.close(fig)


def run(args: argparse.Namespace) -> None:
    features_path = Path(args.features).resolve()
    labels_path = Path(args.labels).resolve()
    splits_path = Path(args.splits).resolve()
    report_dir = Path(args.output_dir).resolve()
    artifact_dir = Path(args.artifact_dir).resolve()
    report_dir.mkdir(parents=True, exist_ok=True)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    esm2_path = _discover_embedding(args.esm2_embeddings, "esm2")
    dnabert2_path = _discover_embedding(args.dnabert2_embeddings, "dnabert2")
    setups = load_feature_setups(features_path, esm2_path, dnabert2_path, args.include_combined)
    if args.setups:
        unknown = set(args.setups) - set(setups)
        if unknown:
            raise ValueError(f"requested unavailable feature setups: {sorted(unknown)}")
        setups = {name: setups[name] for name in args.setups}

    genotype = setups["genotype_only"].frame if "genotype_only" in setups else pd.read_parquet(features_path)
    if not all(str(column).startswith("geno__") for column in genotype.columns):
        genotype = genotype.rename(columns=lambda column: f"geno__{column}")
    labels, metadata = load_metadata(genotype, labels_path, splits_path)
    antibiotics = args.antibiotics or sorted(labels["antibiotic"].unique())
    models = tuple(args.models)
    invalid_models = set(models) - set(BASE_MODELS)
    if invalid_models:
        raise ValueError(f"unknown models: {sorted(invalid_models)}")
    if args.dry_run:
        print(f"validated {len(genotype)} genomes; setups={list(setups)}; antibiotics={antibiotics}")
        return

    comparison_rows: list[dict[str, Any]] = []
    cluster_rows: list[dict[str, Any]] = []
    prediction_rows: list[dict[str, Any]] = []
    disagreement_rows: list[dict[str, Any]] = []
    setup_oof_rows: list[dict[str, Any]] = []
    coefficient_rows: list[dict[str, Any]] = []
    drugs = pd.read_csv(args.drugs_db).fillna("")
    known_markers_by_antibiotic = {
        row.antibiotic: {item for item in str(row.known_markers).split(";") if item}
        for row in drugs.itertuples(index=False)
    }

    for antibiotic in antibiotics:
        antibiotic_labels = labels[labels["antibiotic"] == antibiotic].set_index("genome_id")
        ids = antibiotic_labels.index.intersection(metadata.index, sort=False)
        y_all = (antibiotic_labels.loc[ids, "label"] == "R").astype(int)
        meta = metadata.loc[ids]
        weights_all = pd.Series(
            duplicate_weights(meta["dedup_group_id"]), index=ids, name="duplicate_weight"
        )
        for setup_name, setup in setups.items():
            X_all = setup.frame.loc[ids]
            masks = {name: (meta["split"] == name).to_numpy() for name in ("train", "cal", "test")}
            if any(mask.sum() == 0 for mask in masks.values()):
                raise ValueError(f"{antibiotic}/{setup_name} has an empty predefined split")
            y = y_all.to_numpy()
            weight = weights_all.to_numpy()
            X_train, y_train = X_all.iloc[masks["train"]], y[masks["train"]]
            X_cal, y_cal = X_all.iloc[masks["cal"]], y[masks["cal"]]
            X_test, y_test = X_all.iloc[masks["test"]], y[masks["test"]]
            w_train, w_cal, w_test = weight[masks["train"]], weight[masks["cal"]], weight[masks["test"]]
            groups_train = meta.loc[masks["train"], "cluster_id"].to_numpy()

            fitted: dict[str, Pipeline] = {}
            oof: dict[str, np.ndarray] = {}
            oof_brier: dict[str, float] = {}
            raw_cal: dict[str, np.ndarray] = {}
            raw_test: dict[str, np.ndarray] = {}
            params_by_model: dict[str, dict[str, Any]] = {}
            for model_name in models:
                params, oof_probability, cv_brier = tune_model(
                    model_name,
                    setup,
                    X_train,
                    y_train,
                    groups_train,
                    w_train,
                    args.cv_folds,
                    args.seed,
                    args.quick,
                )
                model = build_model(model_name, params, setup, y_train, args.seed)
                model.fit(X_train, y_train, model__sample_weight=_normalise_weight(w_train))
                fitted[model_name] = model
                if model_name == "l1_logistic":
                    coefficient_rows.extend(
                        _l1_coefficient_rows(
                            model,
                            antibiotic,
                            setup_name,
                            known_markers_by_antibiotic.get(antibiotic, set()),
                        )
                    )
                oof[model_name] = oof_probability
                oof_brier[model_name] = cv_brier
                params_by_model[model_name] = params
                raw_cal[model_name] = model.predict_proba(X_cal)[:, 1]
                raw_test[model_name] = model.predict_proba(X_test)[:, 1]

            vote_weights = _voting_weights(oof_brier, args.voting)
            ensemble_oof = _weighted_average(oof, vote_weights)
            ensemble_cal = _weighted_average(raw_cal, vote_weights)
            ensemble_test = _weighted_average(raw_test, vote_weights)
            ensemble_oof_metrics = compute_metrics(
                y_train, ensemble_oof, w_train, args.no_call_low, args.no_call_high
            )
            setup_oof_rows.append(
                {
                    "antibiotic": antibiotic,
                    "feature_setup": setup_name,
                    "oof_weighted_brier": ensemble_oof_metrics["weighted_brier"],
                    "oof_weighted_balanced_accuracy": ensemble_oof_metrics["weighted_balanced_accuracy"],
                }
            )
            for row in _pairwise_disagreement(oof):
                disagreement_rows.append({"antibiotic": antibiotic, "feature_setup": setup_name, **row})

            probability_sets = {**raw_test, "soft_ensemble": ensemble_test}
            cal_probability_sets = {**raw_cal, "soft_ensemble": ensemble_cal}
            calibrators: dict[str, ScoreCalibrator] = {}
            test_ids = ids[masks["test"]]
            test_meta = meta.loc[test_ids]
            for model_name, raw_probability in probability_sets.items():
                calibrator = ScoreCalibrator(args.calibration).fit(
                    cal_probability_sets[model_name], y_cal, _normalise_weight(w_cal)
                )
                calibrators[model_name] = calibrator
                probability = calibrator.predict(raw_probability)
                metrics = compute_metrics(
                    y_test, probability, w_test, args.no_call_low, args.no_call_high
                )
                comparison_rows.append(
                    {
                        "antibiotic": antibiotic,
                        "feature_setup": setup_name,
                        "model": model_name,
                        "calibration": args.calibration,
                        "voting": args.voting if model_name == "soft_ensemble" else "not_applicable",
                        "n_train": len(y_train),
                        "n_cal": len(y_cal),
                        "n_test": len(y_test),
                        **metrics,
                    }
                )
                for gid, truth, raw_p, calibrated_p, dup_weight, cluster_id, dedup_id in zip(
                    test_ids,
                    y_test,
                    raw_probability,
                    probability,
                    w_test,
                    test_meta["cluster_id"],
                    test_meta["dedup_group_id"],
                ):
                    prediction_rows.append(
                        {
                            "genome_id": gid,
                            "antibiotic": antibiotic,
                            "feature_setup": setup_name,
                            "model": model_name,
                            "cluster_id": cluster_id,
                            "dedup_group_id": dedup_id,
                            "duplicate_weight": dup_weight,
                            "y_true": truth,
                            "raw_probability": raw_p,
                            "probability": calibrated_p,
                            "prediction": int(calibrated_p >= 0.5),
                            "no_call": bool(args.no_call_low <= calibrated_p <= args.no_call_high),
                        }
                    )
                cluster_frame = pd.DataFrame(
                    {
                        "cluster_id": test_meta["cluster_id"].to_numpy(),
                        "y": y_test,
                        "probability": probability,
                        "weight": w_test,
                    }
                )
                for cluster_id, group in cluster_frame.groupby("cluster_id"):
                    cluster_rows.append(
                        {
                            "antibiotic": antibiotic,
                            "feature_setup": setup_name,
                            "model": model_name,
                            "cluster_id": cluster_id,
                            **compute_metrics(
                                group["y"].to_numpy(),
                                group["probability"].to_numpy(),
                                group["weight"].to_numpy(),
                                args.no_call_low,
                                args.no_call_high,
                            ),
                        }
                    )

            artifact = {
                "antibiotic": antibiotic,
                "feature_setup": setup_name,
                "feature_columns": list(setup.frame.columns),
                "models": fitted,
                "model_parameters": params_by_model,
                "voting_weights": vote_weights,
                "calibrators": calibrators,
                "calibration": args.calibration,
                "no_call_band": [args.no_call_low, args.no_call_high],
                "dedup_weighting": "inverse labeled dedup-group size",
            }
            joblib.dump(artifact, artifact_dir / f"{antibiotic}__{setup_name}.joblib")
            print(
                f"finished {antibiotic:15s} {setup_name:35s} "
                f"OOF weighted Brier={ensemble_oof_metrics['weighted_brier']:.4f}"
            )

    comparison = pd.DataFrame(comparison_rows)
    predictions = pd.DataFrame(prediction_rows)
    per_cluster = pd.DataFrame(cluster_rows)
    disagreement = pd.DataFrame(disagreement_rows)
    oof_summary = pd.DataFrame(setup_oof_rows)
    coefficients = pd.DataFrame(coefficient_rows)
    selections = (
        oof_summary.sort_values(
            ["antibiotic", "oof_weighted_brier", "oof_weighted_balanced_accuracy"],
            ascending=[True, True, False],
        )
        .groupby("antibiotic", as_index=False)
        .first()
    )
    selected_pairs = set(zip(selections["antibiotic"], selections["feature_setup"]))
    comparison["selected_by_train_oof"] = [
        (antibiotic, setup) in selected_pairs
        for antibiotic, setup in zip(comparison["antibiotic"], comparison["feature_setup"])
    ]
    predictions["selected_by_train_oof"] = [
        (antibiotic, setup) in selected_pairs
        for antibiotic, setup in zip(predictions["antibiotic"], predictions["feature_setup"])
    ]

    baseline = comparison[
        (comparison["feature_setup"] == "genotype_only")
        & (comparison["model"] == "l1_logistic")
    ][["antibiotic", "weighted_brier", "weighted_balanced_accuracy"]].rename(
        columns={
            "weighted_brier": "baseline_weighted_brier",
            "weighted_balanced_accuracy": "baseline_weighted_balanced_accuracy",
        }
    )
    comparison = comparison.merge(baseline, on="antibiotic", how="left")
    comparison["delta_weighted_brier_vs_genotype_l1"] = (
        comparison["weighted_brier"] - comparison["baseline_weighted_brier"]
    )
    comparison["delta_weighted_balanced_accuracy_vs_genotype_l1"] = (
        comparison["weighted_balanced_accuracy"]
        - comparison["baseline_weighted_balanced_accuracy"]
    )
    comparison = comparison.sort_values(
        ["antibiotic", "selected_by_train_oof", "weighted_brier", "weighted_balanced_accuracy"],
        ascending=[True, False, True, False],
    )

    comparison.to_csv(report_dir / "model_comparison.csv", index=False)
    predictions.to_csv(report_dir / "test_predictions.csv", index=False)
    per_cluster.to_csv(report_dir / "per_cluster_metrics.csv", index=False)
    disagreement.to_csv(report_dir / "oof_model_disagreement.csv", index=False)
    selections.to_csv(report_dir / "selected_feature_setup.csv", index=False)
    oof_summary.to_csv(report_dir / "train_oof_feature_comparison.csv", index=False)
    if coefficients.empty:
        pd.DataFrame(
            columns=[
                "antibiotic",
                "feature_setup",
                "feature",
                "coefficient",
                "absolute_coefficient",
                "direction",
                "known_catalog_marker",
                "interpretation",
            ]
        ).to_csv(report_dir / "l1_coefficients.csv", index=False)
    else:
        coefficients.sort_values(
            ["antibiotic", "feature_setup", "absolute_coefficient"],
            ascending=[True, True, False],
        ).to_csv(report_dir / "l1_coefficients.csv", index=False)
    run_config = {
        "features": str(features_path),
        "labels": str(labels_path),
        "splits": str(splits_path),
        "drugs_db": str(Path(args.drugs_db).resolve()),
        "esm2_embeddings": str(esm2_path) if esm2_path else None,
        "dnabert2_embeddings": str(dnabert2_path) if dnabert2_path else None,
        "feature_setups": list(setups),
        "models": list(models),
        "seed": args.seed,
        "cv_folds": args.cv_folds,
        "calibration": args.calibration,
        "voting": args.voting,
        "duplicate_weighting": "inverse labeled dedup-group size",
        "selection_rule": "lowest train grouped-OOF weighted Brier; weighted balanced accuracy tie-break",
    }
    (report_dir / "run_config.json").write_text(json.dumps(run_config, indent=2))
    _plot_reliability(predictions, selections, report_dir)

    display_columns = [
        "antibiotic",
        "feature_setup",
        "model",
        "selected_by_train_oof",
        "weighted_brier",
        "weighted_balanced_accuracy",
        "weighted_recall_R",
        "weighted_recall_S",
        "weighted_pr_auc",
        "weighted_no_call_rate",
    ]
    print("\nDuplicate-weighted held-out test results (feature setup selected on train OOF only):")
    print(comparison[display_columns].round(4).to_string(index=False))
    print(f"\nWrote reports to {report_dir}")
    print(f"Wrote fitted artifacts to {artifact_dir}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--features", default=str(DEFAULT_FEATURES))
    parser.add_argument("--labels", default=str(DEFAULT_LABELS))
    parser.add_argument("--splits", default=str(DEFAULT_SPLITS))
    parser.add_argument("--drugs-db", default=str(DEFAULT_DRUGS))
    parser.add_argument("--esm2-embeddings", default=None)
    parser.add_argument("--dnabert2-embeddings", default=None)
    parser.add_argument("--include-combined", action="store_true")
    parser.add_argument("--setups", nargs="+", default=None)
    parser.add_argument("--antibiotics", nargs="+", default=None)
    parser.add_argument("--models", nargs="+", default=list(BASE_MODELS))
    parser.add_argument("--cv-folds", type=int, default=5)
    parser.add_argument("--calibration", choices=["sigmoid", "isotonic"], default="sigmoid")
    parser.add_argument("--voting", choices=["uniform", "inverse-brier"], default="uniform")
    parser.add_argument("--no-call-low", type=float, default=0.4)
    parser.add_argument("--no-call-high", type=float, default=0.6)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--quick", action="store_true", help="small grid and two folds for smoke tests")
    parser.add_argument("--dry-run", action="store_true", help="validate paths and schemas without fitting")
    parser.add_argument("--output-dir", default=str(DEFAULT_REPORT_DIR))
    parser.add_argument("--artifact-dir", default=str(DEFAULT_ARTIFACT_DIR))
    return parser


def main(argv: Iterable[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if not 0 <= args.no_call_low < args.no_call_high <= 1:
        raise ValueError("no-call band must satisfy 0 <= low < high <= 1")
    run(args)


if __name__ == "__main__":
    main()
