import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from genome_firewall.model_ensemble import (
    ScoreCalibrator,
    compute_metrics,
    duplicate_weights,
    load_feature_setups,
    load_metadata,
)


class EnsembleDataTests(unittest.TestCase):
    def test_duplicate_family_has_one_total_vote(self):
        groups = pd.Series(["a", "a", "a", "b", "c", "c"])
        weights = duplicate_weights(groups)
        totals = pd.Series(weights).groupby(groups).sum()
        np.testing.assert_allclose(totals.to_numpy(), np.ones(3))

    def test_embedding_setups_are_aligned_and_prefixed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            genotype = pd.DataFrame(
                {"mecA": [1, 0], "blaZ": [0, 1]},
                index=pd.Index(["g1", "g2"], name="genome_id"),
            )
            # Deliberately reverse the embedding order; genome_id must realign it.
            embedding = pd.DataFrame(
                {"emb_0": [20.0, 10.0]},
                index=pd.Index(["g2", "g1"], name="genome_id"),
            )
            genotype_path = root / "features.parquet"
            embedding_path = root / "esm2.parquet"
            genotype.to_parquet(genotype_path)
            embedding.to_parquet(embedding_path)
            setups = load_feature_setups(genotype_path, esm2_path=embedding_path)
            self.assertEqual(
                set(setups), {"genotype_only", "esm2_only", "genotype_plus_esm2"}
            )
            self.assertEqual(setups["esm2_only"].frame.loc["g1", "esm2__emb_0"], 10.0)
            self.assertIn("geno__mecA", setups["genotype_plus_esm2"].frame.columns)

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
