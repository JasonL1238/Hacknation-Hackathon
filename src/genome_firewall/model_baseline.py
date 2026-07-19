"""Per-antibiotic baseline classifier (Stage 3, Module 02 modeling).

Trains one L2-regularized logistic regression per antibiotic on the *train* split
only (grouped, leakage-free — see split.py). Writes the fitted base estimators to
`data/processed/models/base/<antibiotic>.pkl` for `calibrate.py` to wrap.

The RFP recommends exactly this as the dependable core: one regularized LR per drug
over the AMRFinderPlus presence/absence features — CPU-fast, calibratable, and
inspectable (the coefficients feed the report's statistical-evidence category).

Design (logged in docs/DECISIONS.md):
- `class_weight="balanced"`: several drugs are imbalanced (e.g. gentamicin train
  257 R / 1217 S). Balancing keeps recall_R from collapsing to the majority class;
  calibration on the held-out cal split fixes the probability distortion this causes.
- `solver="liblinear"`: exact for small binary L2 problems (144 features), no
  convergence fuss.
- No feature scaling: inputs are already binary 0/1 presence flags.
"""
import pickle
from pathlib import Path

import pandas as pd
from sklearn.linear_model import LogisticRegression

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
FEATURES_PATH = PROCESSED / "features.parquet"
LABELS_PATH = PROCESSED / "labels.csv"
SPLITS_PATH = PROCESSED / "splits.json"
MODELS_DIR = PROCESSED / "models"
BASE_DIR = MODELS_DIR / "base"

C_L2 = 1.0
MAX_ITER = 2000


def load_modeling_frame() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (features indexed by genome_id, labels with a `split` column)."""
    import json

    features = pd.read_parquet(FEATURES_PATH)
    labels = pd.read_csv(LABELS_PATH, dtype={"genome_id": str})
    splits = json.loads(SPLITS_PATH.read_text())
    labels["split"] = labels["genome_id"].map(lambda g: splits.get(g, {}).get("split"))
    labels = labels[labels["split"].notna()]
    return features, labels


def train_one(
    antibiotic: str, features: pd.DataFrame, labels: pd.DataFrame
) -> LogisticRegression | None:
    """Fit an L2 LR for one antibiotic on its train-split genomes. Returns None if
    the train split lacks both classes (can't fit a binary model honestly)."""
    rows = labels[(labels["antibiotic"] == antibiotic) & (labels["split"] == "train")]
    y = (rows["label"] == "R").astype(int)
    if y.nunique() < 2:
        print(f"  {antibiotic}: SKIP — train split has one class only")
        return None
    X = features.loc[rows["genome_id"]].to_numpy()
    # L2 is LogisticRegression's default penalty; naming it explicitly is deprecated
    # in sklearn 1.8+, so we rely on the default and control strength via C.
    clf = LogisticRegression(
        C=C_L2, class_weight="balanced", solver="liblinear", max_iter=MAX_ITER,
    )
    clf.fit(X, y)
    print(f"  {antibiotic}: trained on {len(y)} genomes "
          f"({int(y.sum())} R / {int((1 - y).sum())} S)")
    return clf


def run() -> None:
    features, labels = load_modeling_frame()
    BASE_DIR.mkdir(parents=True, exist_ok=True)

    antibiotics = sorted(labels["antibiotic"].unique())
    print(f"training {len(antibiotics)} per-antibiotic L2 logistic regressions "
          f"on the TRAIN split ({features.shape[1]} features):")
    trained = 0
    for antibiotic in antibiotics:
        clf = train_one(antibiotic, features, labels)
        if clf is None:
            continue
        with open(BASE_DIR / f"{antibiotic}.pkl", "wb") as f:
            pickle.dump(clf, f)
        trained += 1
    print(f"wrote {trained} base models to {BASE_DIR}")


if __name__ == "__main__":
    run()
