"""
Genome Firewall — analysis service (model-integration seam).

The UI never talks to a model directly. It goes through an `AnalysisProvider`
whose method surface mirrors the suggested asynchronous API:

    create_analysis · upload_genome · validate_genome · start_analysis
    get_analysis_status · get_analysis_results · retry_analysis · cancel_analysis

Two implementations are provided:

  • MockAnalysisProvider — the current demo brain. Genome validation is *real*
    lightweight FASTA parsing; predictions are generated from the real
    `db/drugs_saureus.csv` drug catalog using a deterministic, file-seeded
    scenario so a given upload always yields the same, plausible report.
    Processing is a genuine time-based stage machine (no fake percentages).

  • ApiAnalysisProvider — a thin placeholder that shows exactly where a real
    HTTP/async backend drops in. Selected when GENOME_FIREWALL_API_BASE is set.

Switching from mock to real is a provider swap — no page or component changes.
"""

from __future__ import annotations

import hashlib
import os
import time
from datetime import datetime
from pathlib import Path

from app.services.schemas import (
    Analysis, AnalysisStatus, AntibioticResult, EvidenceCategory, GenomeSubmission,
    PIPELINE_STAGES, Prediction, QcStatus, TargetGate,
)

_ROOT = Path(__file__).resolve().parents[2]
_DRUGS_DB = _ROOT / "db" / "drugs_saureus.csv"

# Seconds spent in each non-terminal pipeline stage in the mock (demo pacing).
_STAGE_SECONDS = 1.6

SUPPORTED_SPECIES = {"staphylococcus aureus"}


# ─────────────────────────────────────────────────────────────────────────────
# Drug catalog (real data from db/drugs_saureus.csv)
# ─────────────────────────────────────────────────────────────────────────────
def _load_drugs() -> list[dict]:
    import csv
    rows: list[dict] = []
    if not _DRUGS_DB.exists():
        return rows
    with open(_DRUGS_DB) as f:
        for row in csv.DictReader(f):
            rows.append(row)
    return rows


_DRUGS = _load_drugs()


# ─────────────────────────────────────────────────────────────────────────────
# Real, lightweight FASTA validation (frontend logic behind the service seam)
# ─────────────────────────────────────────────────────────────────────────────
def parse_fasta(data: bytes) -> dict:
    """Parse assembled-contig FASTA bytes into summary genome statistics.

    Returns {ok, error, sequence_count, total_length_bp, n50, gc_content}.
    This is genuine parsing — it never claims to read DNA from a sample, only to
    summarize an already-reconstructed, quality-checked assembly file.
    """
    try:
        text = data.decode("utf-8", errors="ignore")
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": f"Could not decode file: {e}"}

    lengths: list[int] = []
    gc = 0
    total = 0
    cur = 0
    saw_header = False
    for line in text.splitlines():
        if line.startswith(">"):
            saw_header = True
            if cur:
                lengths.append(cur)
                cur = 0
        elif line.strip():
            seq = line.strip().upper()
            cur += len(seq)
            total += len(seq)
            gc += seq.count("G") + seq.count("C")
    if cur:
        lengths.append(cur)

    if not saw_header or not lengths:
        return {"ok": False, "error": "No FASTA records found (missing '>' headers)."}

    lengths.sort(reverse=True)
    half = total / 2
    run = 0
    n50 = lengths[-1]
    for L in lengths:
        run += L
        if run >= half:
            n50 = L
            break

    return {
        "ok": True,
        "error": None,
        "sequence_count": len(lengths),
        "total_length_bp": total,
        "n50": n50,
        "gc_content": round(gc / total, 4) if total else 0.0,
    }


def _seed(*parts: str) -> int:
    h = hashlib.sha256("|".join(parts).encode()).hexdigest()
    return int(h[:12], 16)


# ─────────────────────────────────────────────────────────────────────────────
# Provider interface
# ─────────────────────────────────────────────────────────────────────────────
class AnalysisProvider:
    """Abstract seam. A real backend implements the same surface."""

    name = "abstract"

    def create_analysis(self, *, patient_id: str, case_id: str, isolate_id: str,
                        species: str, model_version: str) -> Analysis:
        raise NotImplementedError

    def validate_genome(self, analysis: Analysis, *, filename: str,
                        data: bytes) -> GenomeSubmission:
        raise NotImplementedError

    def start_analysis(self, analysis: Analysis) -> Analysis:
        raise NotImplementedError

    def get_analysis_status(self, analysis: Analysis) -> Analysis:
        raise NotImplementedError

    def get_analysis_results(self, analysis: Analysis) -> list[AntibioticResult]:
        return analysis.results

    def retry_analysis(self, analysis: Analysis) -> Analysis:
        raise NotImplementedError

    def cancel_analysis(self, analysis: Analysis) -> Analysis:
        analysis.status = AnalysisStatus.CANCELLED.value
        return analysis


# ─────────────────────────────────────────────────────────────────────────────
# Mock provider
# ─────────────────────────────────────────────────────────────────────────────
class MockAnalysisProvider(AnalysisProvider):
    name = "mock"

    # ── creation & upload ──────────────────────────────────────────────────
    def create_analysis(self, *, patient_id, case_id, isolate_id,
                        species, model_version) -> Analysis:
        return Analysis(
            patient_id=patient_id, case_id=case_id, isolate_id=isolate_id,
            species=species, model_version=model_version,
            status=AnalysisStatus.DRAFT.value,
        )

    def validate_genome(self, analysis, *, filename, data) -> GenomeSubmission:
        stats = parse_fasta(data)
        checksum = hashlib.sha256(data).hexdigest()[:16]
        sub = GenomeSubmission(
            filename=filename, size_bytes=len(data), checksum=checksum,
            uploaded_at=datetime.utcnow().isoformat(timespec="seconds") + "Z",
        )
        if not stats["ok"]:
            sub.qc_status = QcStatus.FAILED.value
            sub.qc_warnings = [stats["error"]]
            analysis.genome = sub
            return sub

        sub.sequence_count = stats["sequence_count"]
        sub.total_length_bp = stats["total_length_bp"]
        sub.n50 = stats["n50"]
        sub.gc_content = stats["gc_content"]

        warnings: list[str] = []
        # S. aureus assemblies are ~2.7–2.9 Mbp; flag anything well outside.
        if not (2_400_000 <= sub.total_length_bp <= 3_300_000):
            warnings.append(
                f"Assembly length {sub.total_length_bp:,} bp is outside the expected "
                "S. aureus range (2.4–3.3 Mbp) — verify species and assembly."
            )
        if sub.sequence_count > 400:
            warnings.append(
                f"High contig count ({sub.sequence_count}) suggests a fragmented "
                "assembly; interpret marginal calls with caution."
            )
        if not (0.30 <= sub.gc_content <= 0.36):
            warnings.append(
                f"GC content {sub.gc_content:.1%} is atypical for S. aureus (~33%)."
            )
        sub.qc_warnings = warnings
        sub.qc_status = QcStatus.WARNING.value if warnings else QcStatus.PASSED.value
        analysis.genome = sub
        return sub

    # ── processing (real time-based stage machine) ─────────────────────────
    def start_analysis(self, analysis) -> Analysis:
        analysis.status = AnalysisStatus.PROCESSING.value
        analysis.started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        analysis.current_stage = 0
        analysis.error_message = ""
        return analysis

    def get_analysis_status(self, analysis) -> Analysis:
        if analysis.is_terminal or analysis.status != AnalysisStatus.PROCESSING.value:
            return analysis
        if not analysis.started_at:
            return analysis

        elapsed = self._elapsed(analysis)
        stage = int(elapsed // _STAGE_SECONDS)
        n_stages = len(PIPELINE_STAGES)

        # Deterministic hard-failure scenario: fail at the target-check stage.
        if self._scenario(analysis) == "processing_failure" and stage >= 3:
            analysis.status = AnalysisStatus.FAILED.value
            analysis.current_stage = 3
            analysis.error_message = (
                "Feature extraction did not converge for this assembly — the "
                "contig set could not be annotated. This is a recoverable error; "
                "re-submitting the quality-checked file usually resolves it."
            )
            return analysis

        if stage >= n_stages:
            self._finalize(analysis)
        else:
            analysis.current_stage = min(stage, n_stages - 1)
        return analysis

    def retry_analysis(self, analysis) -> Analysis:
        # A retry produces a NEW run identity but reuses inputs; caller decides
        # whether to clone. Here we just reset this analysis to processing.
        analysis.status = AnalysisStatus.PROCESSING.value
        analysis.started_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        analysis.current_stage = 0
        analysis.error_message = ""
        analysis.results = []
        analysis.completed_at = None
        return analysis

    # ── internals ──────────────────────────────────────────────────────────
    def _elapsed(self, analysis) -> float:
        if not analysis.started_at:
            return 0.0
        try:
            started = datetime.fromisoformat(analysis.started_at.replace("Z", ""))
        except ValueError:
            return 0.0
        return (datetime.utcnow() - started).total_seconds()

    def _scenario(self, analysis) -> str:
        """A stable per-analysis scenario. Explicit override wins (demo seeds)."""
        override = getattr(analysis, "_scenario", None)
        if override:
            return override
        key = (analysis.genome.checksum if analysis.genome else analysis.id)
        buckets = ["resistant", "susceptible", "mixed", "low_confidence",
                   "statistical", "no_call_heavy"]
        return buckets[_seed(key) % len(buckets)]

    def _finalize(self, analysis) -> None:
        analysis.results = self.generate_results(analysis)
        analysis.completed_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
        analysis.current_stage = len(PIPELINE_STAGES) - 1
        n_nocall = analysis.counts()[Prediction.NO_CALL.value]
        analysis.overall_warnings = []
        if n_nocall >= max(3, len(analysis.results) // 2):
            analysis.status = AnalysisStatus.COMPLETED_NO_CALL.value
            analysis.overall_warnings.append(
                "A majority of antibiotics returned no-call — evidence for this "
                "isolate is weak or out-of-distribution. Prioritize laboratory testing."
            )
        else:
            analysis.status = AnalysisStatus.COMPLETED.value

    # ── result generation from the real drug catalog ───────────────────────
    def generate_results(self, analysis) -> list[AntibioticResult]:
        scenario = self._scenario(analysis)
        key = analysis.genome.checksum if analysis.genome else analysis.id
        results: list[AntibioticResult] = []

        for i, drug in enumerate(_DRUGS):
            ab = drug.get("standardized_name") or drug.get("antibiotic", "").capitalize()
            drug_class = drug.get("drug_class", "")
            markers = [m.strip() for m in (drug.get("known_markers") or "").split(";") if m.strip()]
            s = _seed(key, drug.get("antibiotic", ""), scenario)
            roll = (s % 1000) / 1000.0

            res = AntibioticResult(antibiotic=ab, drug_class=drug_class,
                                   target_gate=TargetGate.PASSED.value)

            def _pick_markers(n: int) -> list[str]:
                if not markers:
                    return []
                start = s % len(markers)
                return [markers[(start + k) % len(markers)] for k in range(min(n, len(markers)))]

            if scenario == "resistant":
                pred, conf, ev = Prediction.FAIL, 0.90 + roll * 0.08, EvidenceCategory.KNOWN_MARKER
            elif scenario == "susceptible":
                pred, conf, ev = Prediction.WORK, 0.88 + roll * 0.09, EvidenceCategory.NO_SIGNAL
            elif scenario == "low_confidence":
                pred = Prediction.FAIL if roll > 0.5 else Prediction.WORK
                conf, ev = 0.55 + roll * 0.08, EvidenceCategory.STATISTICAL
            elif scenario == "statistical":
                pred = Prediction.FAIL if roll > 0.45 else Prediction.WORK
                conf, ev = 0.72 + roll * 0.12, EvidenceCategory.STATISTICAL
            elif scenario == "no_call_heavy":
                if roll > 0.75:
                    pred, conf, ev = Prediction.FAIL, 0.83, EvidenceCategory.KNOWN_MARKER
                else:
                    pred, conf, ev = Prediction.NO_CALL, 0.5 + abs(roll - 0.5) * 0.3, EvidenceCategory.CONFLICTING
            else:  # mixed — the most realistic default
                if roll > 0.72:
                    pred, conf, ev = Prediction.FAIL, 0.86 + (roll - 0.72) * 0.4, EvidenceCategory.KNOWN_MARKER
                elif roll > 0.45:
                    pred, conf, ev = Prediction.WORK, 0.84 + (roll - 0.45) * 0.4, EvidenceCategory.NO_SIGNAL
                elif roll > 0.30:
                    pred, conf, ev = Prediction.WORK, 0.78, EvidenceCategory.STATISTICAL
                else:
                    pred, conf, ev = Prediction.NO_CALL, 0.52, EvidenceCategory.CONFLICTING

            res.prediction = pred.value
            res.confidence = round(min(conf, 0.985), 3)
            res.evidence_category = ev.value
            res.confidence_band = (round(max(0.0, res.confidence - 0.05), 3),
                                   round(min(1.0, res.confidence + 0.05), 3))
            res.crossed_threshold = pred is not Prediction.NO_CALL
            res.no_call_threshold_hit = pred is Prediction.NO_CALL

            # Evidence-specific detail + honest language ----------------------
            if ev is EvidenceCategory.KNOWN_MARKER:
                picked = _pick_markers(1 + (s % 2))
                res.supporting_genes = [m for m in picked if "_" not in m]
                res.supporting_mutations = [m for m in picked if "_" in m]
                shown = ", ".join(picked) or "a catalog determinant"
                res.explanation = (
                    f"{shown} detected — a documented {ab.lower()} resistance "
                    "determinant in the reference catalog."
                )
            elif ev is EvidenceCategory.STATISTICAL:
                res.statistical_features = _pick_markers(2)
                res.explanation = (
                    "Driven by a model coefficient over the feature set. This is a "
                    "statistical association, not proven biological causation."
                )
                res.limitations = [
                    "Feature importance is a model artifact and must not be read as "
                    "a biological mechanism."
                ]
            elif ev is EvidenceCategory.NO_SIGNAL:
                res.explanation = (
                    "No resistance markers found; molecular target confirmed present. "
                    "The favorable call rests on the target gate, not absence alone."
                )
            else:  # conflicting / no-call
                res.target_gate = TargetGate.UNKNOWN.value if roll < 0.4 else TargetGate.PASSED.value
                res.explanation = (
                    "Signals are weak or conflicting and the genome sits near or "
                    "outside the training distribution — the model declines to call."
                )
                res.limitations = [
                    "No-call is a valid, honest outcome — not a processing error."
                ]

            if pred is Prediction.NO_CALL:
                res.crossed_threshold = False
            res.limitations.append(
                "Catalog-based detection cannot see novel resistance mechanisms "
                "absent from the reference set."
            )
            results.append(res)

        results.sort(key=lambda r: ({"likely_to_fail": 0, "likely_to_work": 1,
                                     "no_call": 2}.get(r.prediction, 3), r.antibiotic))
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Local real-model provider — runs the trained calibrated models (report.py)
# ─────────────────────────────────────────────────────────────────────────────
class LocalAnalysisProvider(MockAnalysisProvider):
    """Real per-drug predictions from the trained + calibrated models.

    Inherits the mock's *real* FASTA validation and time-based stage machine, and
    replaces only result generation. It resolves the submission to a dataset genome
    by filename stem (a BV-BRC id such as ``1280.16771``), loads that genome's
    AMRFinderPlus feature vector, and runs the real `report.build_report_for_antibiotic`
    per drug — the same calibrated probabilities `evaluate.py` scores on the held-out
    test split.

    If the genome is unknown and live AMRFinderPlus annotation is unavailable, it
    returns an honest all-no-call ("could not annotate") — it never fabricates calls.
    """

    name = "local"

    def generate_results(self, analysis) -> list[AntibioticResult]:
        import json
        from genome_firewall import report

        gid = self._genome_id(analysis)

        # 1) Precomputed real report for a bundled demo genome — use as-is.
        if gid:
            demo = _ROOT / "data" / "processed" / "demo_reports" / f"{gid}.json"
            if demo.exists():
                return self._to_results(json.loads(demo.read_text()))

        # 2) Genome features on disk — run the real models live.
        drugs = {d.get("antibiotic", ""): d for d in _DRUGS}
        fv, cols = self._feature_vector(gid)
        if fv is not None:
            config = report._load_config()
            models = report._load_models()
            legacy = []
            for ab, model in models.items():
                r = report.build_report_for_antibiotic(ab, fv, cols, model, drugs.get(ab, {}), config)
                legacy.append(r)
            return self._to_results(legacy)

        # 3) Cannot annotate → honest all-no-call, never fabricated predictions.
        return self._unannotatable(analysis)

    # ── helpers ─────────────────────────────────────────────────────────────
    def _genome_id(self, analysis) -> str | None:
        if not (analysis.genome and analysis.genome.filename):
            return None
        stem = Path(analysis.genome.filename).name
        for suffix in (".fna", ".fasta", ".fa", ".fna.gz", ".fasta.gz"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        return stem or None

    def _feature_vector(self, gid: str | None):
        """Return (feature_vector, columns) for a known genome id, else (None, None)."""
        if not gid:
            return None, None
        try:
            import pandas as pd
            from genome_firewall import report

            feats = _load_features()
            if feats is None or gid not in feats.index:
                return None, None
            cols = report._load_feature_spec()["columns"]
            return feats.loc[gid].reindex(cols).fillna(0).to_numpy(), cols
        except Exception:  # noqa: BLE001 — any load failure → treat as unavailable
            return None, None

    def _to_results(self, legacy: list[dict]) -> list[AntibioticResult]:
        by_ab = {d.get("antibiotic", ""): d for d in _DRUGS}
        out = []
        for r in legacy:
            drug = by_ab.get(str(r.get("antibiotic", "")).lower(), {})
            r.setdefault("drug_class", drug.get("drug_class", ""))
            out.append(AntibioticResult.from_legacy_report(r))
        out.sort(key=lambda x: ({"likely_to_fail": 0, "likely_to_work": 1,
                                 "no_call": 2}.get(x.prediction, 3), x.antibiotic))
        return out

    def _unannotatable(self, analysis) -> list[AntibioticResult]:
        results = []
        for drug in _DRUGS:
            ab = drug.get("standardized_name") or drug.get("antibiotic", "").capitalize()
            results.append(AntibioticResult(
                antibiotic=ab, drug_class=drug.get("drug_class", ""),
                prediction=Prediction.NO_CALL.value,
                evidence_category=EvidenceCategory.CONFLICTING.value,
                target_gate=TargetGate.UNKNOWN.value,
                no_call_threshold_hit=True,
                explanation=(
                    "This genome is not in the annotated dataset and live "
                    "AMRFinderPlus annotation is unavailable in this environment, so "
                    "resistance features could not be extracted. No prediction is made."
                ),
                limitations=["Confirm with standard laboratory testing."],
            ))
        return results


_FEATURES = None
_FEATURES_LOADED = False


def _load_features():
    """Lazily load the processed feature matrix (indexed by genome_id), or None."""
    global _FEATURES, _FEATURES_LOADED
    if _FEATURES_LOADED:
        return _FEATURES
    _FEATURES_LOADED = True
    try:
        import pandas as pd
        path = _ROOT / "data" / "processed" / "features.parquet"
        _FEATURES = pd.read_parquet(path) if path.exists() else None
    except Exception:  # noqa: BLE001
        _FEATURES = None
    return _FEATURES


# ─────────────────────────────────────────────────────────────────────────────
# Placeholder real-API provider (shows the integration point)
# ─────────────────────────────────────────────────────────────────────────────
class ApiAnalysisProvider(MockAnalysisProvider):
    """Where a real asynchronous backend integrates.

    Inherits the mock's validation/generation so the app stays fully functional
    until each method below is replaced with a real HTTP/websocket call. Every
    override maps 1:1 onto the suggested analysis API.
    """

    name = "api"

    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key or os.environ.get("GENOME_FIREWALL_API_KEY", "")
        # A real implementation would build an authenticated HTTP session here.


_provider: AnalysisProvider | None = None


def get_provider() -> AnalysisProvider:
    """Return the configured analysis provider (memoized).

    Precedence: explicit HTTP API (GENOME_FIREWALL_API_BASE) → forced provider
    (GENOME_FIREWALL_PROVIDER=mock|local) → auto: the real local model when trained
    models are present on disk, else the mock demo brain.
    """
    global _provider
    if _provider is not None:
        return _provider

    base = os.environ.get("GENOME_FIREWALL_API_BASE", "").strip()
    forced = os.environ.get("GENOME_FIREWALL_PROVIDER", "").strip().lower()
    models_present = any((_ROOT / "data" / "processed" / "models").glob("*.pkl")) \
        if (_ROOT / "data" / "processed" / "models").exists() else False

    if base:
        _provider = ApiAnalysisProvider(base)
    elif forced == "mock":
        _provider = MockAnalysisProvider()
    elif forced == "local" or models_present:
        _provider = LocalAnalysisProvider()
    else:
        _provider = MockAnalysisProvider()
    return _provider
