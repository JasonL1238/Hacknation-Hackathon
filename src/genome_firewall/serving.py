"""Serializable soft-voting ensemble — the single model the app serves.

`model_select.py` writes one `SoftVotingEnsemble` per antibiotic to
`data/processed/models/<antibiotic>.pkl`. It honors exactly the contract the
former calibrated baseline did, so `report.py` (the app) and `evaluate.py` load
and use it with no code change:

  * ``predict_proba(X)[:, 1]`` is the calibrated P(resistant) for feature vectors
    given in ``feature_spec.json`` column order (raw binary presence/absence).
  * ``coef_`` (present only when a linear member is in the ensemble) exposes
    coefficients for `report.py`'s statistical-evidence display **only** — they
    are never presented as biological causation (report.py labels them so).

The ensemble members are the top-N base learners chosen on *train* grouped
out-of-fold Brier (never on the test split). Their raw resistance probabilities
are uniformly averaged, then a single isotonic calibrator fit on the dedicated
*cal* split maps that average onto calibrated probabilities. Uniform averaging is
deliberate: it has no parameters to overfit, and the members were already picked
for complementary (diverse) out-of-fold behaviour.
"""

from __future__ import annotations

from typing import Any, Sequence

import numpy as np
import pandas as pd

from genome_firewall.ensemble_calibration import ScoreCalibrator


def _named_model_input(
    X: np.ndarray | pd.DataFrame, feature_columns: Sequence[str] | None
) -> np.ndarray | pd.DataFrame:
    if isinstance(X, pd.DataFrame):
        if feature_columns is None:
            return X
        return X.reindex(columns=list(feature_columns), fill_value=0.0)
    array = np.asarray(X, dtype=float)
    if array.ndim == 1:
        array = array.reshape(1, -1)
    if feature_columns is None:
        return array
    if array.shape[1] != len(feature_columns):
        raise ValueError(f"expected {len(feature_columns)} features, received {array.shape[1]}")
    return pd.DataFrame(array, columns=list(feature_columns))


class CalibratedClassifier:
    """One fitted classifier followed by an out-of-fold score calibrator."""

    def __init__(
        self,
        estimator: Any,
        calibrator: ScoreCalibrator,
        feature_columns: Sequence[str] | None = None,
        classes_: np.ndarray | None = None,
    ) -> None:
        self.estimator = estimator
        self.calibrator = calibrator
        self.feature_columns = list(feature_columns) if feature_columns is not None else None
        self.classes_ = np.asarray(classes_) if classes_ is not None else np.array([0, 1])

    def raw_proba(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        model_input = _named_model_input(X, self.feature_columns)
        return self.estimator.predict_proba(model_input)[:, 1]

    def predict_proba(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        p = np.clip(self.calibrator.predict(self.raw_proba(X)), 0.0, 1.0)
        return np.column_stack([1.0 - p, p])

    def predict(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)


class SoftVotingEnsemble:
    """Calibrated soft vote over fitted base estimators.

    ``weights`` and ``feature_columns`` are optional for backwards compatibility
    with earlier uniformly averaged artifacts. The production genotype ensemble
    supplies both so its inverse-Brier vote reproduces the retained experiment
    and sklearn receives the exact named-column schema used during fitting.
    """

    def __init__(
        self,
        members: list[Any],
        member_names: list[str],
        calibrator: ScoreCalibrator,
        weights: Sequence[float] | None = None,
        feature_columns: Sequence[str] | None = None,
        coef_: np.ndarray | None = None,
        classes_: np.ndarray | None = None,
    ) -> None:
        if not members:
            raise ValueError("SoftVotingEnsemble needs at least one member")
        self.members = list(members)
        self.member_names = list(member_names)
        self.calibrator = calibrator
        if weights is None:
            weights = np.full(len(self.members), 1.0 / len(self.members))
        weights_array = np.asarray(weights, dtype=float)
        if weights_array.shape != (len(self.members),) or np.any(weights_array < 0):
            raise ValueError("weights must be non-negative and match the member count")
        if not np.isfinite(weights_array).all() or weights_array.sum() <= 0:
            raise ValueError("weights must be finite with a positive sum")
        self.weights = weights_array / weights_array.sum()
        self.feature_columns = list(feature_columns) if feature_columns is not None else None
        # report.py reads .coef_ for the (clearly-labelled) statistical-evidence
        # panel. Only set it when a linear member can supply honest coefficients.
        if coef_ is not None:
            self.coef_ = np.asarray(coef_, dtype=float)
        self.classes_ = (
            np.asarray(classes_) if classes_ is not None else np.array([0, 1])
        )

    def _model_input(self, X: np.ndarray | pd.DataFrame) -> np.ndarray | pd.DataFrame:
        return _named_model_input(X, self.feature_columns)

    def raw_proba(self, X: np.ndarray | pd.DataFrame) -> np.ndarray:
        """Uncalibrated ensemble P(R): inverse-Brier weighted member vote."""
        model_input = self._model_input(X)
        columns = [member.predict_proba(model_input)[:, 1] for member in self.members]
        return np.average(np.column_stack(columns), axis=1, weights=self.weights)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        p = self.calibrator.predict(self.raw_proba(X))
        p = np.clip(np.asarray(p, dtype=float), 0.0, 1.0)
        return np.column_stack([1.0 - p, p])

    def predict(self, X: np.ndarray) -> np.ndarray:
        return (self.predict_proba(X)[:, 1] >= 0.5).astype(int)
