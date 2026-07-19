"""
Genome Firewall — typed domain schemas.

The clinical data model is a strict hierarchy:

    Patient
      └─ Case            (a clinical / infection episode)
           └─ Isolate    (a bacterial specimen + confirmed species)
                └─ Analysis   (one genome submission run through the model)
                     └─ AntibioticResult[]   (per-drug decision support)

A new upload or a new model version creates a *new* Analysis — prior analyses
are never overwritten, so a case keeps a full, auditable history.

These dataclasses are the frontend contract. They map cleanly onto the
suggested analysis API response, and onto the existing DATA_SPEC §6 report
object (see `to_legacy_report` / `from_legacy_report`) so a real backend can be
swapped in without touching the UI.

Vocabulary note: the UI uses the explicit, human-readable enum values
(`likely_to_work`, etc.). The legacy pipeline uses short codes (`work`), so the
mapping tables below are the single source of truth for translation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, date
from enum import Enum
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────
class Prediction(str, Enum):
    WORK = "likely_to_work"
    FAIL = "likely_to_fail"
    NO_CALL = "no_call"


class EvidenceCategory(str, Enum):
    KNOWN_MARKER = "known_resistance_marker"     # (i)  catalog hit — biological
    STATISTICAL = "statistical_association"      # (ii) model signal — NOT causal
    NO_SIGNAL = "no_known_resistance_signal"     # (iii) absence of markers
    CONFLICTING = "conflicting_evidence"         # weak / contradictory / OOD


class TargetGate(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


class AnalysisStatus(str, Enum):
    DRAFT = "draft"
    QUEUED = "queued"
    UPLOADING = "uploading"
    VALIDATING = "validating"
    PROCESSING = "processing"
    COMPLETED = "completed"
    COMPLETED_NO_CALL = "completed_with_no_call"   # completed but no-call heavy
    FAILED = "failed"
    CANCELLED = "cancelled"


class CasePriority(str, Enum):
    ROUTINE = "routine"
    URGENT = "urgent"
    CRITICAL = "critical"


class QcStatus(str, Enum):
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    PENDING = "pending"


# Display metadata keyed by enum value — consumed by the UI component layer.
PREDICTION_META = {
    Prediction.WORK.value: {
        "label": "Likely to work", "short": "Works", "icon": "check-circle",
        "tone": "work", "order": 1,
    },
    Prediction.FAIL.value: {
        "label": "Likely to fail", "short": "Fails", "icon": "x-circle",
        "tone": "fail", "order": 0,
    },
    Prediction.NO_CALL.value: {
        "label": "No-call", "short": "No-call", "icon": "minus-circle",
        "tone": "nocall", "order": 2,
    },
}

EVIDENCE_META = {
    EvidenceCategory.KNOWN_MARKER.value: {
        "roman": "i", "icon": "flask", "title": "Known resistance marker",
        "detail": "A gene or point mutation with a documented resistance role "
                  "was detected in the catalog. This is biological evidence.",
    },
    EvidenceCategory.STATISTICAL.value: {
        "roman": "ii", "icon": "bar-chart", "title": "Statistical association only",
        "detail": "Driven by a model coefficient / feature-importance signal. "
                  "This is a statistical pattern — NOT proven biological causation.",
    },
    EvidenceCategory.NO_SIGNAL.value: {
        "roman": "iii", "icon": "circle", "title": "No known resistance signal",
        "detail": "No resistance markers were found. A favorable call is governed "
                  "by the molecular-target gate, never by absence of markers alone.",
    },
    EvidenceCategory.CONFLICTING.value: {
        "roman": "—", "icon": "alert-circle", "title": "Conflicting / insufficient evidence",
        "detail": "Signals disagree, are weak, or the genome is out-of-distribution. "
                  "The model declines to force a verdict.",
    },
}

# Legacy DATA_SPEC §6 code  <->  Prediction enum
_LEGACY_TO_PRED = {"work": Prediction.WORK, "fail": Prediction.FAIL, "nocall": Prediction.NO_CALL}
_PRED_TO_LEGACY = {v: k for k, v in _LEGACY_TO_PRED.items()}
# Legacy roman evidence code  <->  EvidenceCategory
_LEGACY_TO_EV = {
    "i": EvidenceCategory.KNOWN_MARKER,
    "ii": EvidenceCategory.STATISTICAL,
    "iii": EvidenceCategory.NO_SIGNAL,
}
_EV_TO_LEGACY = {v: k for k, v in _LEGACY_TO_EV.items()}


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8].upper()}"


def _now() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ─────────────────────────────────────────────────────────────────────────────
# Records
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class Patient:
    id: str = field(default_factory=lambda: _new_id("PAT"))
    first_name: str = ""
    last_name: str = ""
    mrn: str = ""                       # medical record number (synthetic in demo)
    date_of_birth: str | None = None    # ISO date
    sex: str | None = None
    institution: str = ""
    clinician: str = ""
    care_notes: str = ""
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    is_demo: bool = True

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip() or "Unnamed patient"

    @property
    def age(self) -> int | None:
        if not self.date_of_birth:
            return None
        try:
            dob = date.fromisoformat(self.date_of_birth)
        except ValueError:
            return None
        today = date.today()
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


@dataclass
class Isolate:
    id: str = field(default_factory=lambda: _new_id("ISO"))
    lab_id: str = ""
    species: str = "Staphylococcus aureus"      # confirmed OUTSIDE this system
    gram_stain: str = "Gram-positive"
    gram_notes: str = ""
    specimen_type: str = ""
    specimen_date: str | None = None
    culture_source: str = ""
    assembly_id: str = ""
    sequencing_platform: str = ""
    assembly_quality: str = ""
    lab_notes: str = ""


@dataclass
class GenomeSubmission:
    id: str = field(default_factory=lambda: _new_id("GEN"))
    filename: str = ""
    size_bytes: int = 0
    checksum: str = ""              # short submission fingerprint
    sequence_count: int = 0
    total_length_bp: int = 0
    n50: int = 0
    gc_content: float = 0.0
    qc_status: str = QcStatus.PENDING.value
    qc_warnings: list[str] = field(default_factory=list)
    uploaded_at: str = field(default_factory=_now)


@dataclass
class AntibioticResult:
    antibiotic: str = ""
    drug_class: str = ""
    prediction: str = Prediction.NO_CALL.value
    confidence: float = 0.0                     # calibrated, 0..1
    confidence_band: tuple[float, float] = (0.0, 0.0)
    evidence_category: str = EvidenceCategory.NO_SIGNAL.value
    target_gate: str = TargetGate.UNKNOWN.value
    crossed_threshold: bool = False
    no_call_threshold_hit: bool = False
    supporting_genes: list[str] = field(default_factory=list)
    supporting_mutations: list[str] = field(default_factory=list)
    statistical_features: list[str] = field(default_factory=list)
    explanation: str = ""
    limitations: list[str] = field(default_factory=list)

    # ── legacy DATA_SPEC §6 interop ────────────────────────────────────────
    @classmethod
    def from_legacy_report(cls, r: dict) -> "AntibioticResult":
        pred = _LEGACY_TO_PRED.get(r.get("verdict", "nocall"), Prediction.NO_CALL)
        ev = _LEGACY_TO_EV.get(r.get("evidence_category", "iii"), EvidenceCategory.NO_SIGNAL)
        conf = float(r.get("confidence", 0.0) or 0.0)
        feats = list(r.get("supporting_features", []) or [])
        genes = [f for f in feats if "_" not in f]
        muts = [f for f in feats if "_" in f]
        return cls(
            antibiotic=str(r.get("antibiotic", "")).capitalize(),
            drug_class=r.get("drug_class", ""),
            prediction=pred.value,
            confidence=conf,
            confidence_band=(max(0.0, conf - 0.06), min(1.0, conf + 0.06)),
            evidence_category=ev.value,
            target_gate=(TargetGate.PASSED.value if r.get("target_present")
                         else TargetGate.FAILED.value),
            crossed_threshold=pred is not Prediction.NO_CALL,
            no_call_threshold_hit=pred is Prediction.NO_CALL,
            supporting_genes=genes,
            supporting_mutations=muts,
            explanation="; ".join(r.get("reasons", []) or []),
        )

    def to_legacy_report(self) -> dict:
        pred = Prediction(self.prediction)
        ev = EvidenceCategory(self.evidence_category)
        return {
            "antibiotic": self.antibiotic.lower(),
            "verdict": _PRED_TO_LEGACY.get(pred, "nocall"),
            "confidence": round(self.confidence, 4),
            "evidence_category": _EV_TO_LEGACY.get(ev, "iii"),
            "supporting_features": self.supporting_genes + self.supporting_mutations,
            "target_present": self.target_gate == TargetGate.PASSED.value,
            "reasons": [self.explanation] if self.explanation else [],
        }


@dataclass
class Analysis:
    id: str = field(default_factory=lambda: _new_id("AN"))
    patient_id: str = ""
    case_id: str = ""
    isolate_id: str = ""
    status: str = AnalysisStatus.DRAFT.value
    model_version: str = "genome-firewall-v0.1"
    species: str = "Staphylococcus aureus"
    genome: GenomeSubmission | None = None
    results: list[AntibioticResult] = field(default_factory=list)
    overall_warnings: list[str] = field(default_factory=list)
    requires_lab_confirmation: bool = True
    current_stage: int = 0                       # index into PIPELINE_STAGES
    error_message: str = ""
    created_at: str = field(default_factory=_now)
    started_at: str | None = None
    completed_at: str | None = None

    # convenience roll-ups -----------------------------------------------------
    def counts(self) -> dict[str, int]:
        c = {Prediction.WORK.value: 0, Prediction.FAIL.value: 0, Prediction.NO_CALL.value: 0}
        for r in self.results:
            c[r.prediction] = c.get(r.prediction, 0) + 1
        return c

    @property
    def is_terminal(self) -> bool:
        return self.status in (
            AnalysisStatus.COMPLETED.value, AnalysisStatus.COMPLETED_NO_CALL.value,
            AnalysisStatus.FAILED.value, AnalysisStatus.CANCELLED.value,
        )

    @property
    def is_complete(self) -> bool:
        return self.status in (
            AnalysisStatus.COMPLETED.value, AnalysisStatus.COMPLETED_NO_CALL.value,
        )


@dataclass
class Case:
    id: str = field(default_factory=lambda: _new_id("CASE"))
    patient_id: str = ""
    title: str = ""
    encounter_date: str | None = None
    infection_site: str = ""
    syndrome: str = ""
    priority: str = CasePriority.ROUTINE.value
    antibiotic_exposure: str = ""
    institution: str = ""
    clinician: str = ""
    notes: str = ""
    isolate: Isolate | None = None
    analyses: list[Analysis] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    @property
    def latest_analysis(self) -> Analysis | None:
        return self.analyses[-1] if self.analyses else None


# Canonical pipeline stages — stage-based progress (no fake percentages).
PIPELINE_STAGES: list[tuple[str, str]] = [
    ("Submission received", "Analysis job registered and queued."),
    ("Genome file validated", "FASTA structure, contig count, and length verified."),
    ("Resistance features extracted", "Catalog markers annotated from the assembly."),
    ("Molecular targets checked", "Drug targets confirmed present (target gate)."),
    ("Antibiotic models evaluated", "Per-drug models scored on the feature set."),
    ("Confidence calibrated", "Probabilities mapped to calibrated confidence."),
    ("Explanations assembled", "Evidence categories and reasons compiled."),
    ("Report generated", "Clinical decision-support report finalized."),
]


def to_dict(obj: Any) -> Any:
    """Deep-convert a dataclass tree to plain dicts (for JSON export)."""
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, list):
        return [to_dict(v) for v in obj]
    return obj
