"""Local-model bakeoff → best-3 soft-voting ensemble (Stage 3, Module 02).

Trains a pool of CPU-local classifiers on the AMRFinderPlus presence/absence
features, tunes each with grouped cross-validation *inside the train split*, and
selects a single global trio to soft-vote as the served model — the one the
Streamlit app and `evaluate.py` load from `data/processed/models/<antibiotic>.pkl`.

Rigor rules honored (CLAUDE.md):
  * Selection is on **train grouped out-of-fold (OOF) Brier only** — the test
    split is touched exactly once, by `evaluate.py`, for the final report. Nothing
    here looks at test to choose models, hyperparameters, or the trio.
  * Grouped everything: folds never split a genetic ``cluster_id`` across
    train/validation; near-identical genomes are down-weighted by inverse
    ``dedup_group`` size so a repeated family contributes about one vote.
  * The trio is chosen by a Borda composite of OOF Brier (calibration) and OOF
    balanced accuracy (discrimination) — both judged criteria. Brier alone would
    reward a well-calibrated but poorly-discriminating member; the composite avoids
    that and still favours diverse, complementary members over correlated ones.
  * The winning trio is fixed **globally** (same three learners for every drug) —
    fewer selection decisions on small drugs, and one honest "our model is X"
    story — rather than cherry-picking a different trio per drug.

Outputs (all written, none required to pre-exist):
  reports/model_selection/candidate_oof.csv        per-drug per-candidate OOF metrics
  reports/model_selection/candidate_test.csv        per-drug per-candidate calibrated test metrics
  reports/model_selection/trio_ranking.csv          every 3-combo ranked by mean OOF Brier
  reports/model_selection/ensemble_vs_candidates.csv chosen ensemble vs each member, on test
  reports/model_selection/member_disagreement.csv    pairwise OOF disagreement of chosen members
  reports/model_selection/selection.json             machine-readable summary of the choice
  data/processed/models/<antibiotic>.pkl             the served SoftVotingEnsemble per drug
"""

from __future__ import annotations

import argparse
import itertools
import json
import shutil
import warnings
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from sklearn.ensemble import (
    ExtraTreesClassifier,
    HistGradientBoostingClassifier,
    RandomForestClassifier,
)
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.naive_bayes import BernoulliNB
from sklearn.neighbors import KNeighborsClassifier

from genome_firewall.ensemble_calibration import ScoreCalibrator
from genome_firewall.serving import SoftVotingEnsemble

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
FEATURES_PATH = PROCESSED / "features.parquet"
LABELS_PATH = PROCESSED / "labels.csv"
SPLITS_PATH = PROCESSED / "splits.json"
MODELS_DIR = PROCESSED / "models"
REPORT_DIR = REPO_ROOT / "reports" / "model_selection"

NOCALL_BAND = (0.4, 0.6)
CALIBRATION = "isotonic"
LINEAR_MEMBERS = ("l1_logistic", "l2_logistic")  # preference order for coef_ export


# ─────────────────────────────────────────────────────────────────────────────
# Candidate registry — every learner is CPU-local and takes raw binary features.
# `sw` marks whether .fit accepts sample_weight (kNN does not).
# ─────────────────────────────────────────────────────────────────────────────
def _candidates() -> dict[str, dict[str, Any]]:
    reg: dict[str, dict[str, Any]] = {
        # sklearn 1.9 deprecates penalty= in favour of l1_ratio (0=L2, 1=L1);
        # liblinear supports both, matching the pattern in model_ensemble.py.
        "l2_logistic": {
            "sw": True,
            "grid": [{"C": 0.1}, {"C": 1.0}, {"C": 10.0}],
            "make": lambda p, y, s: LogisticRegression(
                l1_ratio=0.0, class_weight="balanced", solver="liblinear",
                max_iter=2000, random_state=s, **p),
        },
        "l1_logistic": {
            "sw": True,
            "grid": [{"C": 0.1}, {"C": 1.0}],
            "make": lambda p, y, s: LogisticRegression(
                l1_ratio=1.0, class_weight="balanced", solver="liblinear",
                max_iter=3000, random_state=s, **p),
        },
        "hist_gradient_boosting": {
            "sw": True,
            "grid": [
                {"learning_rate": 0.05, "max_leaf_nodes": 7, "l2_regularization": 1.0},
                {"learning_rate": 0.05, "max_leaf_nodes": 15, "l2_regularization": 3.0},
            ],
            "make": lambda p, y, s: HistGradientBoostingClassifier(
                max_iter=250, class_weight="balanced", early_stopping=False,
                random_state=s, **p),
        },
        "random_forest": {
            "sw": True,
            "grid": [{"min_samples_leaf": 1}, {"min_samples_leaf": 3}],
            "make": lambda p, y, s: RandomForestClassifier(
                n_estimators=300, class_weight="balanced_subsample",
                max_features="sqrt", n_jobs=-1, random_state=s, **p),
        },
        "extra_trees": {
            "sw": True,
            "grid": [{"min_samples_leaf": 1}, {"min_samples_leaf": 3}],
            "make": lambda p, y, s: ExtraTreesClassifier(
                n_estimators=300, class_weight="balanced_subsample",
                max_features="sqrt", n_jobs=-1, random_state=s, **p),
        },
        "bernoulli_nb": {
            "sw": True,
            "grid": [{"alpha": 0.5}, {"alpha": 1.0}],
            "make": lambda p, y, s: BernoulliNB(**p),
        },
        "knn": {
            "sw": False,
            "grid": [{"n_neighbors": 5}, {"n_neighbors": 11}],
            "make": lambda p, y, s: KNeighborsClassifier(weights="distance", **p),
        },
    }
    try:
        from xgboost import XGBClassifier

        def _make_xgb(p, y, s):
            neg = max(1, int((y == 0).sum()))
            pos = max(1, int((y == 1).sum()))
            return XGBClassifier(
                n_estimators=300, objective="binary:logistic",
                eval_metric="logloss", tree_method="hist", subsample=0.8,
                colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=3.0,
                scale_pos_weight=neg / pos, random_state=s, n_jobs=1, **p)

        reg["xgboost"] = {
            "sw": True,
            "grid": [{"max_depth": 2, "learning_rate": 0.05},
                     {"max_depth": 3, "learning_rate": 0.05}],
            "make": _make_xgb,
        }
    except ImportError:
        warnings.warn("xgboost unavailable — excluded from the bakeoff", stacklevel=2)

    try:
        from lightgbm import LGBMClassifier

        reg["lightgbm"] = {
            "sw": True,
            "grid": [{"num_leaves": 15, "learning_rate": 0.05},
                     {"num_leaves": 31, "learning_rate": 0.05}],
            "make": lambda p, y, s: LGBMClassifier(
                n_estimators=300, class_weight="balanced", subsample=0.8,
                colsample_bytree=0.8, reg_lambda=3.0, n_jobs=1, verbosity=-1,
                random_state=s, **p),
        }
    except ImportError:
        warnings.warn("lightgbm unavailable — excluded from the bakeoff", stacklevel=2)

    return reg


# ─────────────────────────────────────────────────────────────────────────────
# Data
# ─────────────────────────────────────────────────────────────────────────────
def load_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features = pd.read_parquet(FEATURES_PATH)
    if "genome_id" in features.columns:
        features = features.set_index("genome_id")
    features.index = features.index.astype(str)
    features = features.astype("float32")

    labels = pd.read_csv(LABELS_PATH, dtype={"genome_id": str})
    splits = json.loads(SPLITS_PATH.read_text())
    meta = pd.DataFrame.from_dict(splits, orient="index")
    meta.index = meta.index.astype(str)
    if "dedup_group_id" not in meta.columns:
        meta["dedup_group_id"] = meta.index  # every genome its own group
    return features, labels, meta


def _dedup_weights(dedup_group: pd.Series) -> np.ndarray:
    counts = dedup_group.value_counts()
    return dedup_group.map(lambda v: 1.0 / counts[v]).to_numpy(dtype=float)


def _norm(weight: np.ndarray) -> np.ndarray:
    return weight / np.mean(weight)


# ─────────────────────────────────────────────────────────────────────────────
# Metrics
# ─────────────────────────────────────────────────────────────────────────────
def _metrics(y: np.ndarray, prob_r: np.ndarray, weight: np.ndarray | None = None) -> dict:
    pred = (prob_r >= 0.5).astype(int)
    both = len(np.unique(y)) == 2
    called = (prob_r < NOCALL_BAND[0]) | (prob_r > NOCALL_BAND[1])
    out = {
        "n": int(len(y)),
        "n_R": int(y.sum()),
        "n_S": int((1 - y).sum()),
        "balanced_accuracy": float(balanced_accuracy_score(y, pred)) if both else float("nan"),
        "recall_R": float(recall_score(y, pred, pos_label=1, zero_division=0)),
        "recall_S": float(recall_score(y, pred, pos_label=0, zero_division=0)),
        "f1": float(f1_score(y, pred, pos_label=1, zero_division=0)),
        "auroc": float(roc_auc_score(y, prob_r)) if both else float("nan"),
        "pr_auc": float(average_precision_score(y, prob_r)) if both else float("nan"),
        "brier": float(brier_score_loss(y, prob_r)),
        "nocall_rate": float((~called).mean()),
        "accuracy_on_called": float((pred[called] == y[called]).mean()) if called.any() else float("nan"),
    }
    if weight is not None:
        out["weighted_brier"] = float(brier_score_loss(y, prob_r, sample_weight=weight))
        out["weighted_balanced_accuracy"] = (
            (recall_score(y, pred, pos_label=1, sample_weight=weight, zero_division=0)
             + recall_score(y, pred, pos_label=0, sample_weight=weight, zero_division=0)) / 2
            if both else float("nan"))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Grouped folds and per-candidate tuning (train split only)
# ─────────────────────────────────────────────────────────────────────────────
def _grouped_folds(y: np.ndarray, groups: np.ndarray, n_splits: int, seed: int):
    n_splits = min(n_splits, len(np.unique(groups)))
    while n_splits >= 2:
        splitter = StratifiedGroupKFold(n_splits=n_splits, shuffle=True, random_state=seed)
        folds = list(splitter.split(np.zeros(len(y)), y, groups))
        if all(len(np.unique(y[tr])) == 2 for tr, _ in folds):
            return folds
        n_splits -= 1
    raise ValueError("cannot build grouped folds with both classes in every train fold")


def _fit(estimator: Any, X: np.ndarray, y: np.ndarray, w: np.ndarray, sw: bool) -> Any:
    if sw:
        estimator.fit(X, y, sample_weight=_norm(w))
    else:
        estimator.fit(X, y)
    return estimator


def tune_candidate(
    spec: dict, X: np.ndarray, y: np.ndarray, groups: np.ndarray, w: np.ndarray,
    folds: list, seed: int,
) -> tuple[dict, np.ndarray, float]:
    """Grid-search a candidate by dedup-weighted grouped-OOF Brier. Returns
    (best_params, best_oof_probabilities, best_oof_weighted_brier)."""
    best = (None, None, float("inf"))
    for params in spec["grid"]:
        oof = np.full(len(y), np.nan)
        for tr, va in folds:
            model = spec["make"](params, y[tr], seed)
            _fit(model, X[tr], y[tr], w[tr], spec["sw"])
            oof[va] = model.predict_proba(X[va])[:, 1]
        score = brier_score_loss(y, oof, sample_weight=w)
        if score < best[2]:
            best = (params, oof, float(score))
    return best


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────
def run(args: argparse.Namespace) -> None:
    features, labels, meta = load_data()
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    reg = _candidates()
    if args.quick:
        reg = {k: {**v, "grid": v["grid"][:1]} for k, v in reg.items()}
    cand_names = list(reg)
    antibiotics = args.antibiotics or sorted(labels["antibiotic"].unique())
    print(f"candidates: {cand_names}")
    print(f"antibiotics: {antibiotics}\n")

    # Per drug: OOF probs per candidate, fitted-on-full-train models, cal/test slices.
    drug_state: dict[str, dict] = {}
    cand_oof_rows: list[dict] = []
    cand_test_rows: list[dict] = []

    for ab in antibiotics:
        rows = labels[labels["antibiotic"] == ab].set_index("genome_id")
        ids = rows.index.intersection(features.index)
        y_all = (rows.loc[ids, "label"] == "R").astype(int).to_numpy()
        m = meta.loc[ids]
        X_all = features.loc[ids].to_numpy()
        w_all = _dedup_weights(m["dedup_group_id"])
        split = m["split"].to_numpy()
        tr, ca, te = split == "train", split == "cal", split == "test"
        if not (tr.any() and ca.any() and te.any()):
            print(f"{ab}: SKIP — missing a split"); continue
        if len(np.unique(y_all[tr])) < 2 or len(np.unique(y_all[ca])) < 2:
            print(f"{ab}: SKIP — train or cal split has one class only"); continue

        folds = _grouped_folds(
            y_all[tr], m.loc[tr, "cluster_id"].to_numpy(),
            2 if args.quick else args.cv_folds, args.seed)

        oof_by_cand: dict[str, np.ndarray] = {}
        fitted_by_cand: dict[str, Any] = {}
        raw_cal: dict[str, np.ndarray] = {}
        raw_test: dict[str, np.ndarray] = {}
        for name in cand_names:
            spec = reg[name]
            params, oof, oof_brier = tune_candidate(
                spec, X_all[tr], y_all[tr], m.loc[tr, "cluster_id"].to_numpy(),
                w_all[tr], folds, args.seed)
            model = spec["make"](params, y_all[tr], args.seed)
            _fit(model, X_all[tr], y_all[tr], w_all[tr], spec["sw"])
            oof_by_cand[name] = oof
            fitted_by_cand[name] = model
            raw_cal[name] = model.predict_proba(X_all[ca])[:, 1]
            raw_test[name] = model.predict_proba(X_all[te])[:, 1]

            oof_m = _metrics(y_all[tr], oof, w_all[tr])
            cand_oof_rows.append({"antibiotic": ab, "candidate": name,
                                  "params": json.dumps(params),
                                  "oof_weighted_brier": oof_m["weighted_brier"],
                                  "oof_brier": oof_m["brier"],
                                  "oof_balanced_accuracy": oof_m["balanced_accuracy"],
                                  "oof_weighted_balanced_accuracy": oof_m["weighted_balanced_accuracy"]})

            # Single-candidate calibrated test metrics (for the writeup only —
            # NOT used to pick anything).
            cal = ScoreCalibrator(CALIBRATION).fit(raw_cal[name], y_all[ca], _norm(w_all[ca]))
            test_prob = cal.predict(raw_test[name])
            cand_test_rows.append({"antibiotic": ab, "candidate": name,
                                   **{k: v for k, v in _metrics(y_all[te], test_prob).items()}})
            print(f"  {ab:14s} {name:22s} OOF wBrier={oof_m['weighted_brier']:.4f}")

        drug_state[ab] = {
            "y_tr": y_all[tr], "y_ca": y_all[ca], "y_te": y_all[te],
            "w_tr": w_all[tr], "w_ca": w_all[ca], "w_te": w_all[te],
            "oof": oof_by_cand, "fitted": fitted_by_cand,
            "raw_cal": raw_cal, "raw_test": raw_test,
            "X_tr": X_all[tr], "X_ca": X_all[ca],
        }

    solved = list(drug_state)
    if not solved:
        raise SystemExit("no antibiotic had all three splits with both classes")

    # ── Global trio selection: minimise mean-across-drugs OOF Brier ──────────
    # Uniform average of member OOF probabilities per drug; average the per-drug
    # OOF Brier across drugs. Purely train-derived; test is never consulted.
    size = args.ensemble_size
    trio_rows: list[dict] = []
    for combo in itertools.combinations(cand_names, size):
        per_drug_brier, per_drug_bacc = [], []
        for ab in solved:
            st = drug_state[ab]
            avg = np.mean([st["oof"][c] for c in combo], axis=0)
            per_drug_brier.append(brier_score_loss(st["y_tr"], avg, sample_weight=st["w_tr"]))
            mm = _metrics(st["y_tr"], avg, st["w_tr"])
            per_drug_bacc.append(mm["weighted_balanced_accuracy"])
        trio_rows.append({"members": "+".join(combo),
                          "mean_oof_weighted_brier": float(np.mean(per_drug_brier)),
                          "mean_oof_weighted_balanced_accuracy": float(np.nanmean(per_drug_bacc))})
    # Discrimination-aware selection: the rubric weights balanced accuracy AND
    # calibration, so we rank trios on BOTH the ensemble's mean OOF Brier (lower
    # better) and mean OOF weighted balanced accuracy (higher better) and pick the
    # best average rank (Borda). Selecting on Brier alone rewards a well-calibrated
    # but poorly-discriminating member (e.g. a forest that predicts near base-rate);
    # the composite avoids that. Everything here is train-OOF only — test is never
    # consulted to choose the trio, its members, or their hyperparameters.
    trio_df = pd.DataFrame(trio_rows)
    trio_df["rank_brier"] = trio_df["mean_oof_weighted_brier"].rank(ascending=True)
    trio_df["rank_balanced_accuracy"] = trio_df[
        "mean_oof_weighted_balanced_accuracy"].rank(ascending=False)
    trio_df["selection_score"] = (
        trio_df["rank_brier"] + trio_df["rank_balanced_accuracy"]) / 2
    trio_df = trio_df.sort_values(
        ["selection_score", "mean_oof_weighted_brier"],
        ascending=[True, True]).reset_index(drop=True)
    winner = tuple(trio_df.iloc[0]["members"].split("+"))
    print(f"\nselected global trio (best OOF Brier+balanced-accuracy composite): {winner}")

    # ── Build + persist the served ensemble per drug ─────────────────────────
    if not args.dry_run:
        backup = MODELS_DIR / "baseline_backup"
        backup.mkdir(exist_ok=True)
        for old in MODELS_DIR.glob("*.pkl"):
            shutil.copy2(old, backup / old.name)

    ens_vs_rows: list[dict] = []
    disagreement_rows: list[dict] = []
    for ab in solved:
        st = drug_state[ab]
        members = [st["fitted"][c] for c in winner]
        # coefficients for report.py's statistical-evidence panel (labelled
        # non-causal there) — from the preferred linear member if present.
        coef = None
        for lin in LINEAR_MEMBERS:
            if lin in winner and hasattr(st["fitted"][lin], "coef_"):
                coef = np.asarray(st["fitted"][lin].coef_); break

        avg_cal = np.mean([st["raw_cal"][c] for c in winner], axis=0)
        avg_test = np.mean([st["raw_test"][c] for c in winner], axis=0)
        calibrator = ScoreCalibrator(CALIBRATION).fit(avg_cal, st["y_ca"], _norm(st["w_ca"]))
        ensemble = SoftVotingEnsemble(members, list(winner), calibrator, coef_=coef)

        # Ensemble vs each member on the held-out test split (reporting only).
        ens_test_prob = calibrator.predict(avg_test)
        ens_vs_rows.append({"antibiotic": ab, "model": "soft_ensemble",
                            **_metrics(st["y_te"], ens_test_prob)})
        for c in winner:
            cal = ScoreCalibrator(CALIBRATION).fit(st["raw_cal"][c], st["y_ca"], _norm(st["w_ca"]))
            ens_vs_rows.append({"antibiotic": ab, "model": c,
                                **_metrics(st["y_te"], cal.predict(st["raw_test"][c]))})
        for a, b in itertools.combinations(winner, 2):
            disagreement_rows.append({"antibiotic": ab, "model_a": a, "model_b": b,
                                      "oof_disagreement_rate": float(np.mean(
                                          (st["oof"][a] >= 0.5) != (st["oof"][b] >= 0.5))),
                                      "oof_prob_correlation": float(np.corrcoef(
                                          st["oof"][a], st["oof"][b])[0, 1])})

        if not args.dry_run:
            import pickle
            with open(MODELS_DIR / f"{ab}.pkl", "wb") as f:
                pickle.dump(ensemble, f)

    # ── Write experiment tables ──────────────────────────────────────────────
    pd.DataFrame(cand_oof_rows).to_csv(REPORT_DIR / "candidate_oof.csv", index=False)
    pd.DataFrame(cand_test_rows).to_csv(REPORT_DIR / "candidate_test.csv", index=False)
    trio_df.to_csv(REPORT_DIR / "trio_ranking.csv", index=False)
    pd.DataFrame(ens_vs_rows).to_csv(REPORT_DIR / "ensemble_vs_candidates.csv", index=False)
    pd.DataFrame(disagreement_rows).to_csv(REPORT_DIR / "member_disagreement.csv", index=False)
    (REPORT_DIR / "selection.json").write_text(json.dumps({
        "candidates": cand_names,
        "antibiotics": solved,
        "ensemble_size": size,
        "selected_trio": list(winner),
        "selection_rule": "best Borda composite of mean-across-drugs dedup-weighted "
                          "train grouped-OOF Brier (lower) and weighted balanced "
                          "accuracy (higher); OOF Brier tie-break; global fixed trio",
        "calibration": CALIBRATION,
        "nocall_band": list(NOCALL_BAND),
        "seed": args.seed,
        "trio_ranking_top5": trio_df.head(5).to_dict(orient="records"),
    }, indent=2))

    print(f"\nwrote experiment tables to {REPORT_DIR}")
    if not args.dry_run:
        print(f"wrote served ensembles to {MODELS_DIR} (old baselines backed up)")
        print("run `make evaluate` to regenerate metrics.json + plots from the ensemble")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--antibiotics", nargs="+", default=None)
    p.add_argument("--cv-folds", type=int, default=5)
    p.add_argument("--ensemble-size", type=int, default=3)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--quick", action="store_true", help="one param per candidate, 2 folds")
    p.add_argument("--dry-run", action="store_true", help="select but do not overwrite models")
    return p


def main(argv=None) -> None:
    run(build_parser().parse_args(argv))


if __name__ == "__main__":
    main()
