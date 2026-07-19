import json
import tempfile
import unittest
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from genome_firewall.model_ensemble import (
    FeatureSetup,
    ScoreCalibrator,
    build_model,
    compute_metrics,
    duplicate_weights,
    load_feature_setups,
    load_metadata,
)
from genome_firewall.serving import CalibratedClassifier, SoftVotingEnsemble


class _FixedProbabilityModel:
    def __init__(self, probability):
        self.probability = probability

    def predict_proba(self, X):
        p = np.full(len(X), self.probability)
        return np.column_stack([1 - p, p])


class _IdentityCalibrator:
    def predict(self, probability):
        return np.asarray(probability)


class EnsembleDataTests(unittest.TestCase):
    def test_l1_logistic_uses_l1_penalty(self):
        setup = FeatureSetup(
            name="genotype_only",
            frame=pd.DataFrame({"geno__x": [0, 1]}),
            genotype_columns=("geno__x",),
        )
        model = build_model("l1_logistic", {"C": 1.0}, setup, np.array([0, 1]), 42)
        self.assertEqual(model.named_steps["model"].l1_ratio, 1.0)

    def test_duplicate_family_has_one_total_vote(self):
        groups = pd.Series(["a", "a", "a", "b", "c", "c"])
        weights = duplicate_weights(groups)
        totals = pd.Series(weights).groupby(groups).sum()
        np.testing.assert_allclose(totals.to_numpy(), np.ones(3))

    def test_genotype_setup_is_indexed_and_prefixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            genotype = pd.DataFrame(
                {"mecA": [1, 0], "blaZ": [0, 1]},
                index=pd.Index(["g1", "g2"], name="genome_id"),
            )
            genotype_path = root / "features.parquet"
            genotype.to_parquet(genotype_path)
            setups = load_feature_setups(genotype_path)
            self.assertEqual(set(setups), {"genotype_only"})
            self.assertEqual(list(setups["genotype_only"].frame.index), ["g1", "g2"])
            self.assertIn("geno__mecA", setups["genotype_only"].frame.columns)

    def test_cluster_leakage_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            genotype = pd.DataFrame(
                {"geno__x": [0, 1]}, index=pd.Index(["g1", "g2"], name="genome_id")
            )
            labels = pd.DataFrame(
                {
                    "genome_id": ["g1", "g2"],
                    "antibiotic": ["drug", "drug"],
                    "label": ["S", "R"],
                }
            )
            labels_path = root / "labels.csv"
            splits_path = root / "splits.json"
            labels.to_csv(labels_path, index=False)
            splits_path.write_text(
                json.dumps(
                    {
                        "g1": {"split": "train", "cluster_id": 1, "dedup_group_id": 1},
                        "g2": {"split": "test", "cluster_id": 1, "dedup_group_id": 2},
                    }
                )
            )
            with self.assertRaisesRegex(ValueError, "cluster_id spans"):
                load_metadata(genotype, labels_path, splits_path)


class EnsembleMetricTests(unittest.TestCase):
    def test_calibrated_classifier_accepts_frozen_numpy_schema(self):
        model = CalibratedClassifier(
            estimator=_FixedProbabilityModel(0.7),
            calibrator=_IdentityCalibrator(),
            feature_columns=["geno__a", "geno__b"],
        )
        self.assertAlmostEqual(model.predict_proba(np.array([[1, 0]]))[0, 1], 0.7)

    def test_serving_ensemble_uses_saved_weights_and_named_schema(self):
        ensemble = SoftVotingEnsemble(
            members=[_FixedProbabilityModel(0.2), _FixedProbabilityModel(0.8)],
            member_names=["low", "high"],
            weights=[0.25, 0.75],
            feature_columns=["geno__a", "geno__b"],
            calibrator=_IdentityCalibrator(),
        )
        probability = ensemble.predict_proba(np.array([[1, 0]]))[0, 1]
        self.assertAlmostEqual(probability, 0.65)
    def test_calibrator_artifact_round_trip(self):
        raw = np.array([0.05, 0.2, 0.7, 0.95])
        y = np.array([0, 0, 1, 1])
        calibrator = ScoreCalibrator("sigmoid").fit(raw, y, np.ones(4))
        self.assertEqual(
            calibrator.__class__.__module__, "genome_firewall.ensemble_calibration"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "calibrator.joblib"
            joblib.dump(calibrator, path)
            restored = joblib.load(path)
        np.testing.assert_allclose(restored.predict(raw), calibrator.predict(raw))

    def test_calibrator_and_metrics_are_bounded(self):
        raw = np.array([0.05, 0.2, 0.7, 0.95])
        y = np.array([0, 0, 1, 1])
        weight = np.ones(4)
        probability = ScoreCalibrator("sigmoid").fit(raw, y, weight).predict(raw)
        self.assertTrue(np.all((0 <= probability) & (probability <= 1)))
        metrics = compute_metrics(y, probability, weight, 0.4, 0.6)
        self.assertEqual(metrics["n"], 4)
        self.assertGreaterEqual(metrics["weighted_brier"], 0)
        self.assertLessEqual(metrics["weighted_brier"], 1)


if __name__ == "__main__":
    unittest.main()
