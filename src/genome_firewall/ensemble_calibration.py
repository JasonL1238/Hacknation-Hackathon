"""Serializable probability calibration for ensemble model artifacts."""

from __future__ import annotations

from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression


class ScoreCalibrator:
    """Calibrate one-dimensional model probabilities with a stable import path."""

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
