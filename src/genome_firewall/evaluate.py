"""Held-out evaluation + calibration/PR plots (Stage 3, Module 02/03).

Scores the calibrated per-antibiotic models on the *test* split only (grouped,
leakage-free) and writes `data/processed/metrics.json` (DATA_SPEC §7) plus
`reports/reliability.png` and `reports/pr_curves.png`.

Every test cluster is, by construction, a genetic group unseen during training (no
cluster spans splits — split.py). So the headline per-antibiotic test numbers already
measure unseen-group generalization; the `per_group` section additionally breaks each
drug down by individual genetic cluster so the spread across groups is visible, not
hidden inside one average (RFP: "performance broken down by genetically related
groups ... groups not seen during training").

Reported per drug (RFP success criteria): balanced accuracy; recall_R and recall_S
separately; F1; AUROC; PR-AUC (matters under imbalance); Brier score; and the
no-call accounting — no_call rate and accuracy-on-called using the config no-call
probability band.
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # headless — no display needed
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pickle  # noqa: E402
from sklearn.calibration import calibration_curve  # noqa: E402
from sklearn.metrics import (  # noqa: E402
    average_precision_score, balanced_accuracy_score, brier_score_loss,
    f1_score, precision_recall_curve, recall_score, roc_auc_score,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED / "models"
REPORTS_DIR = REPO_ROOT / "reports"
CONFIG_PATH = REPO_ROOT / "config" / "saureus.yaml"
METRICS_PATH = PROCESSED / "metrics.json"

MIN_GROUP_TEST = 10  # smallest per-cluster test count worth reporting a group metric


def _load():
    import yaml
    from genome_firewall.model_baseline import load_modeling_frame

    features, labels = load_modeling_frame()
    splits = json.loads((PROCESSED / "splits.json").read_text())
    labels["cluster_id"] = labels["genome_id"].map(
        lambda g: splits.get(g, {}).get("cluster_id")
    )
    config = yaml.safe_load(CONFIG_PATH.read_text())
    band = config.get("nocall", {}).get("prob_band", [0.4, 0.6])
    return features, labels, band


def _metrics(y_true: np.ndarray, prob_r: np.ndarray, band: list[float]) -> dict:
    """Full metric set for one (drug or group) slice. `prob_r` = calibrated P(R)."""
    pred = (prob_r >= 0.5).astype(int)
    both = len(np.unique(y_true)) == 2

    # No-call accounting: p inside the band is a no-call; the rest are "called".
    called = (prob_r < band[0]) | (prob_r > band[1])
    n = len(y_true)
    acc_called = (
        float((pred[called] == y_true[called]).mean()) if called.any() else None
    )
    return {
        "n": int(n),
        "n_R": int(y_true.sum()),
        "n_S": int((1 - y_true).sum()),
        "balanced_accuracy": round(float(balanced_accuracy_score(y_true, pred)), 4),
        "recall_R": round(float(recall_score(y_true, pred, pos_label=1, zero_division=0)), 4),
        "recall_S": round(float(recall_score(y_true, pred, pos_label=0, zero_division=0)), 4),
        "f1": round(float(f1_score(y_true, pred, pos_label=1, zero_division=0)), 4),
        "auroc": round(float(roc_auc_score(y_true, prob_r)), 4) if both else None,
        "pr_auc": round(float(average_precision_score(y_true, prob_r)), 4) if both else None,
        "brier": round(float(brier_score_loss(y_true, prob_r)), 4),
        "nocall_rate": round(float((~called).mean()), 4),
        "accuracy_on_called": round(acc_called, 4) if acc_called is not None else None,
    }


def evaluate() -> dict:
    features, labels, band = _load()
    model_pkls = sorted(MODELS_DIR.glob("*.pkl"))
    if not model_pkls:
        raise SystemExit("no calibrated models — run `make train && make calibrate` first")

    per_antibiotic, per_group, reliability = {}, {}, {}
    for pkl in model_pkls:
        antibiotic = pkl.stem
        with open(pkl, "rb") as f:
            model = pickle.load(f)
        rows = labels[(labels["antibiotic"] == antibiotic) & (labels["split"] == "test")]
        if rows.empty:
            continue
        y = (rows["label"] == "R").astype(int).to_numpy()
        prob_r = model.predict_proba(features.loc[rows["genome_id"]].to_numpy())[:, 1]

        per_antibiotic[antibiotic] = _metrics(y, prob_r, band)
        reliability[antibiotic] = (y, prob_r)

        # Per genetic group (individual test clusters, all unseen in training).
        groups = []
        for cid, gidx in rows.reset_index(drop=True).groupby("cluster_id").groups.items():
            gi = list(gidx)
            if len(gi) < MIN_GROUP_TEST:
                continue
            gm = _metrics(y[gi], prob_r[gi], band)
            gm["cluster_id"] = int(cid)
            groups.append(gm)
        per_group[antibiotic] = sorted(groups, key=lambda d: -d["n"])

    metrics = {
        "split": "test (grouped, held-out; every cluster unseen in training)",
        "config": {
            "nocall_band": band,
            "calibration": "isotonic (cal split)",
            "n_features": int(features.shape[1]),
        },
        "per_antibiotic": per_antibiotic,
        "per_group": per_group,
        "macro_avg": {
            k: round(float(np.mean([m[k] for m in per_antibiotic.values() if m[k] is not None])), 4)
            for k in ("balanced_accuracy", "recall_R", "recall_S", "f1",
                      "auroc", "pr_auc", "brier", "nocall_rate")
        },
    }
    METRICS_PATH.write_text(json.dumps(metrics, indent=2))
    _plot_reliability(reliability)
    _plot_pr(reliability)
    return metrics


def _plot_reliability(reliability: dict) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6, 6))
    ax.plot([0, 1], [0, 1], "k--", lw=1, label="perfectly calibrated")
    for antibiotic, (y, prob_r) in reliability.items():
        frac_pos, mean_pred = calibration_curve(y, prob_r, n_bins=8, strategy="quantile")
        ax.plot(mean_pred, frac_pos, "o-", ms=4, label=antibiotic)
    ax.set_xlabel("mean predicted P(resistant)")
    ax.set_ylabel("observed fraction resistant")
    ax.set_title("Reliability diagram — held-out test split")
    ax.legend(fontsize=8, loc="upper left")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "reliability.png", dpi=130)
    plt.close(fig)


def _plot_pr(reliability: dict) -> None:
    fig, ax = plt.subplots(figsize=(6, 6))
    for antibiotic, (y, prob_r) in reliability.items():
        if len(np.unique(y)) < 2:
            continue
        prec, rec, _ = precision_recall_curve(y, prob_r)
        ap = average_precision_score(y, prob_r)
        ax.plot(rec, prec, lw=1.5, label=f"{antibiotic} (AP={ap:.2f})")
    ax.set_xlabel("recall (resistant)")
    ax.set_ylabel("precision (resistant)")
    ax.set_title("Precision–recall — held-out test split")
    ax.legend(fontsize=8, loc="lower left")
    fig.tight_layout()
    fig.savefig(REPORTS_DIR / "pr_curves.png", dpi=130)
    plt.close(fig)


def run() -> None:
    metrics = evaluate()
    print(f"wrote {METRICS_PATH}")
    print(f"wrote {REPORTS_DIR / 'reliability.png'} and {REPORTS_DIR / 'pr_curves.png'}")
    print("\nper-antibiotic (held-out test):")
    hdr = ("drug", "n", "bal_acc", "rec_R", "rec_S", "auroc", "pr_auc", "brier", "nocall")
    print("  {:<14}{:>5}{:>9}{:>7}{:>7}{:>7}{:>8}{:>7}{:>8}".format(*hdr))
    for ab, m in metrics["per_antibiotic"].items():
        print("  {:<14}{:>5}{:>9}{:>7}{:>7}{:>7}{:>8}{:>7}{:>8}".format(
            ab, m["n"], m["balanced_accuracy"], m["recall_R"], m["recall_S"],
            m["auroc"] if m["auroc"] is not None else "-",
            m["pr_auc"] if m["pr_auc"] is not None else "-",
            m["brier"], m["nocall_rate"]))
    ma = metrics["macro_avg"]
    print(f"\nmacro avg: bal_acc={ma['balanced_accuracy']} auroc={ma['auroc']} "
          f"pr_auc={ma['pr_auc']} brier={ma['brier']} nocall_rate={ma['nocall_rate']}")


if __name__ == "__main__":
    run()
