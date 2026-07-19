"""Probability calibration on the dedicated calibration split (Stage 3, Module 02).

For each base model from `model_baseline.py`, wraps it in an isotonic
`CalibratedClassifierCV(cv="prefit")` fit on the *cal* split — never on train or
test (CLAUDE.md rigor rule 2). Writes the calibrated estimator to
`data/processed/models/<antibiotic>.pkl`, the object `report.py` loads and calls
`predict_proba` on.

`report.py` also inspects `.coef_` to surface statistical-evidence (category ii)
features. `CalibratedClassifierCV` doesn't expose `coef_`, so we copy the base LR's
coefficients onto the calibrated object — probabilities come from the calibrator,
while the coefficients stay available for explanation only (they are NOT presented as
biological cause; report.py labels them "NOT proven causal").

Isotonic vs sigmoid (logged in docs/DECISIONS.md): isotonic is the more flexible,
non-parametric fit the RFP-style reliability target rewards, but it can overfit a
small cal split. Gentamicin's cal split has only 43 R — the thinnest here — so its
calibration curve should be read with that caveat; `evaluate.py` reports Brier on the
held-out test set precisely so this is measured, not assumed.
"""
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.calibration import CalibratedClassifierCV
from sklearn.frozen import FrozenEstimator

from genome_firewall.model_baseline import load_modeling_frame

REPO_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = REPO_ROOT / "data" / "processed"
MODELS_DIR = PROCESSED / "models"
BASE_DIR = MODELS_DIR / "base"

CALIBRATION_METHOD = "isotonic"


def calibrate_one(
    antibiotic: str, base_model, features: pd.DataFrame, labels: pd.DataFrame
):
    """Fit an isotonic calibrator for one prefit model on its cal-split genomes.
    Returns None if the cal split lacks both classes."""
    rows = labels[(labels["antibiotic"] == antibiotic) & (labels["split"] == "cal")]
    y = (rows["label"] == "R").astype(int)
    if y.nunique() < 2:
        print(f"  {antibiotic}: SKIP — cal split has one class only")
        return None
    X = features.loc[rows["genome_id"]].to_numpy()
    # sklearn 1.9 removed cv="prefit"; FrozenEstimator wraps the already-fitted base
    # model so .fit() below trains only the calibrator, never touching train data.
    calibrated = CalibratedClassifierCV(
        FrozenEstimator(base_model), method=CALIBRATION_METHOD
    )
    calibrated.fit(X, y)
    # Copy base coefficients through for report.py's statistical-evidence display only.
    calibrated.coef_ = np.asarray(base_model.coef_)
    print(f"  {antibiotic}: calibrated ({CALIBRATION_METHOD}) on {len(y)} cal genomes "
          f"({int(y.sum())} R / {int((1 - y).sum())} S)")
    return calibrated


def run() -> None:
    features, labels = load_modeling_frame()
    base_pkls = sorted(BASE_DIR.glob("*.pkl"))
    if not base_pkls:
        raise SystemExit("no base models found — run `make train` first")

    print(f"calibrating {len(base_pkls)} models on the CAL split:")
    written = 0
    for pkl in base_pkls:
        antibiotic = pkl.stem
        with open(pkl, "rb") as f:
            base_model = pickle.load(f)
        calibrated = calibrate_one(antibiotic, base_model, features, labels)
        if calibrated is None:
            continue
        with open(MODELS_DIR / f"{antibiotic}.pkl", "wb") as f:
            pickle.dump(calibrated, f)
        written += 1
    print(f"wrote {written} calibrated models to {MODELS_DIR}")


if __name__ == "__main__":
    run()
