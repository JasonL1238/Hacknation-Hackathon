"""
BioShield AI — demo data store (session-state repository).

Holds the full clinical hierarchy (patients → cases → isolates → analyses →
results) in Streamlit session state and seeds it with clearly-labeled SYNTHETIC
demonstration data. No real protected health information is ever expected here,
and nothing in this module is written to `data/`, `db/`, or `reports/`.

The same method surface would sit in front of Supabase for a persistent
deployment; the in-memory implementation keeps the demo zero-setup and lets a
reviewer explore every state without a database.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import streamlit as st

from app.services.analysis_service import MockAnalysisProvider
from app.services.schemas import (
    Analysis, AnalysisStatus, Case, CasePriority, GenomeSubmission, Isolate,
    Patient, QcStatus,
)

_KEY = "gf_store"


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds") + "Z"


class Store:
    """Thin repository over a dict held in st.session_state."""

    def __init__(self, data: dict[str, Any]) -> None:
        self._d = data

    # ── patients ────────────────────────────────────────────────────────────
    @property
    def patients(self) -> list[Patient]:
        return self._d["patients"]

    def list_patients(self) -> list[Patient]:
        return sorted(self.patients, key=lambda p: p.updated_at, reverse=True)

    def get_patient(self, pid: str) -> Patient | None:
        return next((p for p in self.patients if p.id == pid), None)

    def create_patient(self, patient: Patient) -> Patient:
        self.patients.append(patient)
        self.log(f"Patient {patient.full_name} created", patient.id)
        return patient

    def update_patient(self, patient: Patient) -> None:
        patient.updated_at = _iso(datetime.utcnow())

    # ── cases ─────────────────────────────────────────────────────────────────
    @property
    def cases(self) -> list[Case]:
        return self._d["cases"]

    def list_cases(self, patient_id: str | None = None) -> list[Case]:
        cs = self.cases if patient_id is None else [c for c in self.cases if c.patient_id == patient_id]
        return sorted(cs, key=lambda c: c.updated_at, reverse=True)

    def get_case(self, cid: str) -> Case | None:
        return next((c for c in self.cases if c.id == cid), None)

    def create_case(self, case: Case) -> Case:
        self.cases.append(case)
        p = self.get_patient(case.patient_id)
        if p:
            self.update_patient(p)
        self.log(f"Case '{case.title}' created", case.patient_id, case.id)
        return case

    # ── analyses ──────────────────────────────────────────────────────────────
    def list_analyses(self, *, patient_id: str | None = None,
                      case_id: str | None = None) -> list[Analysis]:
        out: list[Analysis] = []
        for c in self.cases:
            if patient_id and c.patient_id != patient_id:
                continue
            if case_id and c.id != case_id:
                continue
            out.extend(c.analyses)
        return sorted(out, key=lambda a: a.created_at, reverse=True)

    def get_analysis(self, aid: str) -> Analysis | None:
        for c in self.cases:
            for a in c.analyses:
                if a.id == aid:
                    return a
        return None

    def case_of_analysis(self, aid: str) -> Case | None:
        for c in self.cases:
            if any(a.id == aid for a in c.analyses):
                return c
        return None

    def add_analysis(self, case: Case, analysis: Analysis) -> Analysis:
        case.analyses.append(analysis)
        case.updated_at = _iso(datetime.utcnow())
        p = self.get_patient(case.patient_id)
        if p:
            self.update_patient(p)
        self.log(f"Analysis {analysis.id} submitted", case.patient_id, case.id, analysis.id)
        return analysis

    # ── activity feed ─────────────────────────────────────────────────────────
    def log(self, message: str, patient_id: str = "", case_id: str = "",
            analysis_id: str = "") -> None:
        self._d["activity"].insert(0, {
            "message": message, "patient_id": patient_id, "case_id": case_id,
            "analysis_id": analysis_id, "at": _iso(datetime.utcnow()),
        })
        del self._d["activity"][200:]

    @property
    def activity(self) -> list[dict]:
        return self._d["activity"]

    # ── notifications ─────────────────────────────────────────────────────────
    @property
    def notifications(self) -> list[dict]:
        return self._d["notifications"]


# ─────────────────────────────────────────────────────────────────────────────
# Access + seeding
# ─────────────────────────────────────────────────────────────────────────────
def get_store() -> Store:
    if _KEY not in st.session_state:
        st.session_state[_KEY] = _seed()
    return Store(st.session_state[_KEY])


def _mk_genome(filename: str, seqs: int, length: int, gc: float, n50: int,
               status: str, warnings: list[str] | None = None) -> GenomeSubmission:
    import hashlib
    return GenomeSubmission(
        filename=filename, size_bytes=length + 60 * seqs,
        checksum=hashlib.sha256(filename.encode()).hexdigest()[:16],
        sequence_count=seqs, total_length_bp=length, n50=n50, gc_content=gc,
        qc_status=status, qc_warnings=warnings or [],
    )


def _seed() -> dict[str, Any]:
    """Build the synthetic demonstration dataset. Runs once per session."""
    prov = MockAnalysisProvider()
    now = datetime.utcnow()

    data: dict[str, Any] = {"patients": [], "cases": [], "activity": [],
                            "notifications": []}
    store = Store(data)

    def finalize(a: Analysis, scenario: str, days_ago: float) -> Analysis:
        """Turn a fresh analysis into a completed historical record."""
        a._scenario = scenario  # type: ignore[attr-defined]
        created = now - timedelta(days=days_ago)
        a.created_at = _iso(created)
        a.started_at = _iso(created + timedelta(seconds=3))
        a.results = prov.generate_results(a)
        a.current_stage = 7
        a.completed_at = _iso(created + timedelta(seconds=18))
        n_nocall = a.counts()["no_call"]
        if n_nocall >= max(3, len(a.results) // 2):
            a.status = AnalysisStatus.COMPLETED_NO_CALL.value
            a.overall_warnings = [
                "A majority of antibiotics returned no-call — evidence for this "
                "isolate is weak or out-of-distribution. Prioritize laboratory testing."
            ]
        else:
            a.status = AnalysisStatus.COMPLETED.value
        return a

    # ── Patient 1 — MRSA bacteremia, completed resistant report ──────────────
    p1 = Patient(first_name="Amara", last_name="Okonkwo", mrn="MRN-48213",
                 date_of_birth="1958-03-14", sex="Female",
                 institution="Demo General Hospital", clinician="Dr. R. Feldman")
    data["patients"].append(p1)
    c1 = Case(patient_id=p1.id, title="MRSA bloodstream infection",
              encounter_date=_iso(now - timedelta(days=6))[:10],
              infection_site="Bloodstream", syndrome="Bacteremia",
              priority=CasePriority.CRITICAL.value, institution=p1.institution,
              clinician=p1.clinician,
              antibiotic_exposure="Empiric vancomycin started day 1",
              notes="Central line-associated. Persistent fevers.")
    c1.isolate = Isolate(lab_id="LAB-7781", specimen_type="Blood culture",
                         specimen_date=_iso(now - timedelta(days=6))[:10],
                         culture_source="Peripheral + line", assembly_id="ASM-SA-0042",
                         sequencing_platform="Illumina NovaSeq (paired-end)",
                         assembly_quality="Passed QC (external)")
    a1 = Analysis(patient_id=p1.id, case_id=c1.id, isolate_id=c1.isolate.id)
    a1.genome = _mk_genome("SA_bcx_0042.fasta", 61, 2_842_311, 0.329, 214_882,
                           QcStatus.PASSED.value)
    finalize(a1, "resistant", days_ago=5)
    c1.analyses.append(a1)
    data["cases"].append(c1)

    # ── Patient 2 — SSTI, susceptible (favorable) report ─────────────────────
    p2 = Patient(first_name="Liang", last_name="Chen", mrn="MRN-30947",
                 date_of_birth="1991-11-02", sex="Male",
                 institution="Demo General Hospital", clinician="Dr. S. Ortega")
    data["patients"].append(p2)
    c2 = Case(patient_id=p2.id, title="Skin & soft-tissue infection",
              encounter_date=_iso(now - timedelta(days=3))[:10],
              infection_site="Left lower leg", syndrome="Cellulitis / abscess",
              priority=CasePriority.ROUTINE.value, institution=p2.institution,
              clinician=p2.clinician, notes="Post-incision & drainage.")
    c2.isolate = Isolate(lab_id="LAB-8120", specimen_type="Wound swab",
                        specimen_date=_iso(now - timedelta(days=3))[:10],
                        culture_source="Abscess aspirate", assembly_id="ASM-SA-0058",
                        sequencing_platform="Oxford Nanopore (R10)",
                        assembly_quality="Passed QC (external)")
    a2 = Analysis(patient_id=p2.id, case_id=c2.id, isolate_id=c2.isolate.id)
    a2.genome = _mk_genome("SA_wound_0058.fasta", 44, 2_781_004, 0.331, 288_190,
                          QcStatus.PASSED.value)
    finalize(a2, "susceptible", days_ago=2)
    c2.analyses.append(a2)
    data["cases"].append(c2)

    # ── Patient 3 — no-call-heavy (out-of-distribution) ──────────────────────
    p3 = Patient(first_name="Fatima", last_name="Al-Rashid", mrn="MRN-55620",
                 date_of_birth="1974-06-21", sex="Female",
                 institution="Demo Regional Lab", clinician="Dr. P. Njoroge")
    data["patients"].append(p3)
    c3 = Case(patient_id=p3.id, title="Prosthetic joint infection",
              encounter_date=_iso(now - timedelta(days=8))[:10],
              infection_site="Right hip prosthesis", syndrome="PJI",
              priority=CasePriority.URGENT.value, institution=p3.institution,
              clinician=p3.clinician, notes="Atypical growth; possible mixed flora.")
    c3.isolate = Isolate(lab_id="LAB-6644", specimen_type="Synovial fluid",
                        specimen_date=_iso(now - timedelta(days=8))[:10],
                        culture_source="Intra-op tissue", assembly_id="ASM-SA-0071",
                        sequencing_platform="Illumina MiSeq",
                        assembly_quality="Passed with warnings (external)")
    a3 = Analysis(patient_id=p3.id, case_id=c3.id, isolate_id=c3.isolate.id)
    a3.genome = _mk_genome("SA_pji_0071.fasta", 512, 3_150_002, 0.345, 41_220,
                          QcStatus.WARNING.value,
                          ["High contig count (512) suggests a fragmented assembly."])
    finalize(a3, "no_call_heavy", days_ago=4)
    c3.analyses.append(a3)
    data["cases"].append(c3)

    # ── Patient 4 — statistical-only associations + low confidence ───────────
    p4 = Patient(first_name="Grace", last_name="Mbeki", mrn="MRN-21455",
                 date_of_birth="2003-09-09", sex="Female",
                 institution="Demo General Hospital", clinician="Dr. R. Feldman")
    data["patients"].append(p4)
    c4 = Case(patient_id=p4.id, title="Ventilator-associated pneumonia",
              encounter_date=_iso(now - timedelta(days=2))[:10],
              infection_site="Lower respiratory tract", syndrome="VAP",
              priority=CasePriority.URGENT.value, institution=p4.institution,
              clinician=p4.clinician, notes="ICU day 6; intubated.")
    c4.isolate = Isolate(lab_id="LAB-9002", specimen_type="Endotracheal aspirate",
                        specimen_date=_iso(now - timedelta(days=2))[:10],
                        culture_source="Deep respiratory", assembly_id="ASM-SA-0090",
                        sequencing_platform="Illumina NovaSeq (paired-end)",
                        assembly_quality="Passed QC (external)")
    a4 = Analysis(patient_id=p4.id, case_id=c4.id, isolate_id=c4.isolate.id)
    a4.genome = _mk_genome("SA_vap_0090.fasta", 58, 2_808_770, 0.330, 176_540,
                          QcStatus.PASSED.value)
    finalize(a4, "statistical", days_ago=1)
    c4.analyses.append(a4)
    data["cases"].append(c4)

    # ── Patient 5 — LIVE: one processing + one failed processing ─────────────
    p5 = Patient(first_name="Marcus", last_name="Bianchi", mrn="MRN-77310",
                 date_of_birth="1966-12-30", sex="Male",
                 institution="Demo General Hospital", clinician="Dr. S. Ortega")
    data["patients"].append(p5)
    c5 = Case(patient_id=p5.id, title="Osteomyelitis follow-up",
              encounter_date=_iso(now)[:10], infection_site="Tibia",
              syndrome="Chronic osteomyelitis", priority=CasePriority.ROUTINE.value,
              institution=p5.institution, clinician=p5.clinician,
              notes="Repeat isolate after 4 weeks of therapy.")
    c5.isolate = Isolate(lab_id="LAB-9188", specimen_type="Bone biopsy",
                        specimen_date=_iso(now)[:10], culture_source="Debridement",
                        assembly_id="ASM-SA-0104",
                        sequencing_platform="Illumina NovaSeq (paired-end)",
                        assembly_quality="Passed QC (external)")
    # processing (animates): started just now
    a5 = Analysis(patient_id=p5.id, case_id=c5.id, isolate_id=c5.isolate.id,
                  status=AnalysisStatus.PROCESSING.value)
    a5.genome = _mk_genome("SA_osteo_0104.fasta", 52, 2_795_500, 0.331, 201_300,
                          QcStatus.PASSED.value)
    a5._scenario = "mixed"  # type: ignore[attr-defined]
    a5.started_at = _iso(now)
    a5.current_stage = 0
    c5.analyses.append(a5)
    # failed processing (recoverable)
    a5b = Analysis(patient_id=p5.id, case_id=c5.id, isolate_id=c5.isolate.id,
                   status=AnalysisStatus.FAILED.value)
    a5b.genome = _mk_genome("SA_osteo_0104_run1.fasta", 340, 2_930_000, 0.336, 22_100,
                           QcStatus.WARNING.value)
    a5b._scenario = "processing_failure"  # type: ignore[attr-defined]
    a5b.created_at = _iso(now - timedelta(hours=3))
    a5b.started_at = _iso(now - timedelta(hours=3))
    a5b.current_stage = 3
    a5b.error_message = (
        "Feature extraction did not converge for this assembly — the contig set "
        "could not be annotated. This is a recoverable error; re-submitting the "
        "quality-checked file usually resolves it."
    )
    c5.analyses.append(a5b)
    data["cases"].append(c5)

    # ── Patient 6 — failed genome validation (bad upload) ────────────────────
    p6 = Patient(first_name="Yuki", last_name="Tanaka", mrn="MRN-13998",
                 date_of_birth="1985-04-18", sex="Female",
                 institution="Demo Regional Lab", clinician="Dr. P. Njoroge")
    data["patients"].append(p6)
    c6 = Case(patient_id=p6.id, title="Catheter-related infection",
              encounter_date=_iso(now - timedelta(days=1))[:10],
              infection_site="Vascular catheter", syndrome="CRBSI",
              priority=CasePriority.ROUTINE.value, institution=p6.institution,
              clinician=p6.clinician, notes="Re-upload pending corrected assembly.")
    c6.isolate = Isolate(lab_id="LAB-9241", specimen_type="Catheter tip",
                        specimen_date=_iso(now - timedelta(days=1))[:10],
                        culture_source="Line tip", assembly_id="ASM-SA-0112",
                        sequencing_platform="Illumina MiSeq",
                        assembly_quality="Failed QC (external)")
    a6 = Analysis(patient_id=p6.id, case_id=c6.id, isolate_id=c6.isolate.id,
                  status=AnalysisStatus.FAILED.value)
    a6.genome = _mk_genome("SA_line_0112.fasta", 0, 0, 0.0, 0,
                          QcStatus.FAILED.value,
                          ["No FASTA records found (missing '>' headers). The file "
                           "may be a raw-read FASTQ or a corrupted upload."])
    a6.created_at = _iso(now - timedelta(hours=20))
    a6.error_message = "Genome validation failed — see quality checks."
    c6.analyses.append(a6)
    data["cases"].append(c6)

    # ── Activity feed (most-recent first) ────────────────────────────────────
    data["activity"] = [
        {"message": f"Analysis {a5.id} started processing", "patient_id": p5.id,
         "case_id": c5.id, "analysis_id": a5.id, "at": _iso(now)},
        {"message": f"Report reviewed for {p4.full_name}", "patient_id": p4.id,
         "case_id": c4.id, "analysis_id": a4.id, "at": _iso(now - timedelta(hours=5))},
        {"message": f"Genome validation failed for {p6.full_name}", "patient_id": p6.id,
         "case_id": c6.id, "analysis_id": a6.id, "at": _iso(now - timedelta(hours=20))},
        {"message": f"Analysis {a2.id} completed", "patient_id": p2.id,
         "case_id": c2.id, "analysis_id": a2.id, "at": _iso(now - timedelta(days=2))},
        {"message": f"Case '{c1.title}' created", "patient_id": p1.id,
         "case_id": c1.id, "analysis_id": "", "at": _iso(now - timedelta(days=6))},
    ]

    # ── Notifications ─────────────────────────────────────────────────────────
    data["notifications"] = [
        {"kind": "processing", "title": "Analysis in progress",
         "body": f"{a5.id} for {p5.full_name} is being evaluated.",
         "analysis_id": a5.id, "unread": True},
        {"kind": "failed", "title": "Genome validation failed",
         "body": f"{p6.full_name}: upload rejected — re-submit a corrected FASTA.",
         "analysis_id": a6.id, "unread": True},
        {"kind": "no_call", "title": "No-call–heavy report",
         "body": f"{p3.full_name}: majority no-call — prioritize lab testing.",
         "analysis_id": a3.id, "unread": True},
    ]

    return data
