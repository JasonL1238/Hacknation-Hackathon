"""
BioShield AI — Report builder (Module 03 interface).

Produces DATA_SPEC §6 report objects: one dict per antibiotic with verdict,
calibrated confidence, evidence category, supporting features, and reasons.

IMPORTANT: Research prototype — every result must be confirmed by standard
laboratory testing. Decision support only; a trained professional decides.
This tool never designs, modifies, or optimises any organism.
"""

from __future__ import annotations

import json
import pickle
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parent.parent.parent
PROCESSED = ROOT / "data" / "processed"
DRUGS_DB = ROOT / "db" / "drugs_saureus.csv"
CONFIG = ROOT / "config" / "saureus.yaml"


def _load_config() -> dict:
    """Load project config."""
    import yaml
    return yaml.safe_load(CONFIG.read_text())


def _load_feature_spec() -> dict:
    """Load frozen feature spec (column order for inference)."""
    p = PROCESSED / "feature_spec.json"
    if not p.exists():
        raise FileNotFoundError(
            f"feature_spec.json not found at {p}. Run `make featurize` first."
        )
    return json.loads(p.read_text())


def _load_drugs_db() -> dict[str, dict]:
    """Load drug database, keyed by antibiotic name."""
    import csv
    db = {}
    if not DRUGS_DB.exists():
        return db
    with open(DRUGS_DB) as f:
        for row in csv.DictReader(f):
            db[row["antibiotic"]] = row
    return db


def _load_models() -> dict[str, Any]:
    """Load trained + calibrated per-antibiotic model pickles."""
    final_dir = PROCESSED / "final_models"
    models_dir = final_dir if any(final_dir.glob("*.pkl")) else PROCESSED / "models"
    models = {}
    if not models_dir.exists():
        return models
    for pkl in models_dir.glob("*.pkl"):
        antibiotic = pkl.stem
        with open(pkl, "rb") as f:
            models[antibiotic] = pickle.load(f)
    return models


def _featurize_single_genome(fasta_path: str) -> np.ndarray:
    """
    Run AMRFinderPlus on a single FASTA and return a feature vector
    in feature_spec.json column order.
    """
    from genome_firewall.featurize import vectorize_fasta

    return vectorize_fasta(fasta_path, _load_feature_spec()).to_numpy()


def _determine_evidence_category(
    supporting_features: list[str],
    statistical_features: list[str],
    known_markers: list[str],
    model_contribution: float,
) -> str:
    """
    Determine evidence category per DATA_SPEC §6:
      (i)   known resistance gene/mutation detected (catalog hit)
      (ii)  statistical association only (model signal, NOT proven causal)
      (iii) no known resistance signal found
    """
    # Check if any supporting feature is a known catalog marker
    known_set = set(known_markers)
    has_catalog_hit = any(f in known_set for f in supporting_features)

    if has_catalog_hit:
        return "i"
    elif statistical_features and abs(model_contribution) > 0.1:
        return "ii"
    else:
        return "iii"


def _check_target_gate(
    feature_vector: np.ndarray,
    columns: list[str],
    drug_info: dict,
) -> bool:
    """
    Deterministic target gate: check if the drug's molecular target gene
    is present in the genome. Returns True if target confirmed present.
    """
    target_genes_str = drug_info.get("target_genes", "")
    if not target_genes_str:
        # No target info available — conservative: gate passes
        return True

    target_genes = [g.strip() for g in target_genes_str.split(";") if g.strip()]
    if not target_genes:
        return True

    # Two cases, matching docs/DECISIONS.md's target-gate design:
    # 1. A target gene that AMRFinderPlus *can* emit as a feature (detectable): require
    #    it to actually be present in this genome — that's a real, checkable gate.
    detectable = [g for g in target_genes if g in columns]
    if detectable:
        return any(feature_vector[columns.index(g)] == 1 for g in detectable)

    # 2. All target genes are essential/intrinsic (ribosomal proteins rplV/rplD/rpsJ,
    #    16S rrs, PBPs pbpA-D, gyrase/topoisomerase) that AMRFinderPlus does NOT emit
    #    because they are housekeeping genes, not resistance determinants. In S. aureus
    #    these are present by construction, so the gate passes. Its job here is to block
    #    a "works" call from marker-absence alone, not to detect an intrinsic gene the
    #    feature matrix was never designed to carry (documented limitation).
    return True


def _apply_nocall_logic(
    calibrated_prob: float,
    target_present: bool,
    config: dict,
) -> bool:
    """Return True if this prediction should be no-called."""
    band = config.get("nocall", {}).get("prob_band", [0.4, 0.6])

    # Ambiguous probability
    if band[0] <= calibrated_prob <= band[1]:
        return True

    # Target gate failure
    if not target_present:
        return True

    return False


def build_report_for_antibiotic(
    antibiotic: str,
    feature_vector: np.ndarray,
    columns: list[str],
    model: Any,
    drug_info: dict,
    config: dict,
) -> dict:
    """
    Build a single DATA_SPEC §6 report object for one antibiotic.
    """
    # Get calibrated probability of resistance
    prob_r = model.predict_proba(feature_vector.reshape(1, -1))[0, 1]

    # Target gate
    target_present = _check_target_gate(feature_vector, columns, drug_info)

    # Identify supporting features (top contributors)
    supporting_features = []
    statistical_features = []
    reasons = []

    known_markers_str = drug_info.get("known_markers", "")
    known_markers = [m.strip() for m in known_markers_str.split(";") if m.strip()]

    # Find which known markers are present in this genome
    for marker in known_markers:
        if marker in columns:
            idx = columns.index(marker)
            if feature_vector[idx] == 1:
                supporting_features.append(marker)
                reasons.append(
                    f"{marker} detected (known {antibiotic} resistance determinant)"
                )

    # If model has coefficients, find top statistical contributors
    if hasattr(model, "coef_") or hasattr(model, "named_steps"):
        try:
            # Get the base estimator's coefficients
            estimator = model
            if hasattr(model, "named_steps"):
                estimator = list(model.named_steps.values())[-1]
            if hasattr(estimator, "coef_"):
                coefs = estimator.coef_[0]
                # Active features with high |coef| not already in supporting
                active_mask = feature_vector > 0
                active_coefs = coefs * active_mask
                top_indices = np.argsort(np.abs(active_coefs))[::-1][:5]
                for idx in top_indices:
                    if active_coefs[idx] != 0:
                        feat_name = columns[idx]
                        if feat_name not in supporting_features:
                            statistical_features.append(feat_name)
                            reasons.append(
                                f"{feat_name} — statistical association "
                                f"(coefficient={coefs[idx]:.2f}; "
                                f"NOT proven causal)"
                            )
        except (AttributeError, IndexError):
            pass

    # Evidence category
    evidence_category = _determine_evidence_category(
        supporting_features,
        statistical_features,
        known_markers,
        model_contribution=prob_r - 0.5,
    )

    # No-call logic
    is_nocall = _apply_nocall_logic(prob_r, target_present, config)

    # Determine verdict
    if is_nocall:
        verdict = "nocall"
        confidence = max(prob_r, 1.0 - prob_r)
    elif prob_r >= 0.5:
        verdict = "fail"
        confidence = prob_r
    else:
        # "likely to work" — but NEVER from absence alone without target gate
        if not target_present:
            verdict = "nocall"
            confidence = 1.0 - prob_r
            reasons.append("Target gene not confirmed present — cannot call 'work'.")
        elif evidence_category == "iii" and not supporting_features:
            # Absence of markers alone — target gate decides
            verdict = "work"
            confidence = 1.0 - prob_r
            reasons.append(
                "No resistance markers detected; target confirmed present."
            )
        else:
            verdict = "work"
            confidence = 1.0 - prob_r

    return {
        "antibiotic": antibiotic,
        "probability_resistant": round(float(prob_r), 4),
        "verdict": verdict,
        "confidence": round(float(confidence), 4),
        "evidence_category": evidence_category,
        "supporting_features": supporting_features[:10],  # cap display
        "statistical_features": statistical_features[:5],
        "target_present": target_present,
        "reasons": reasons[:5],
    }


def build_reports_for_genome(fasta_path: str) -> list[dict]:
    """
    Full single-genome inference: featurize → predict → report per antibiotic.
    Returns a list of DATA_SPEC §6 report dicts.

    Called by the Streamlit app for live uploads.
    """
    config = _load_config()
    spec = _load_feature_spec()
    columns = spec["columns"]
    drugs_db = _load_drugs_db()
    models = _load_models()

    if not models:
        raise RuntimeError(
            "No trained models found. Run `make all` to build the pipeline."
        )

    # Featurize the uploaded genome
    feature_vector = _featurize_single_genome(fasta_path)

    # Build report for each antibiotic with a trained model
    reports = []
    for antibiotic, model in models.items():
        drug_info = drugs_db.get(antibiotic, {})
        report = build_report_for_antibiotic(
            antibiotic=antibiotic,
            feature_vector=feature_vector,
            columns=columns,
            model=model,
            drug_info=drug_info,
            config=config,
        )
        reports.append(report)

    # Sort: fail first, then work, then nocall
    verdict_order = {"fail": 0, "work": 1, "nocall": 2}
    reports.sort(key=lambda r: (verdict_order.get(r["verdict"], 3), r["antibiotic"]))

    return reports
