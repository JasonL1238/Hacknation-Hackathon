"""
Database operations for BioShield AI.

CRUD operations against Supabase PostgreSQL with Row Level Security.
All operations require an authenticated user (user_id from session).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.supabase_client import get_supabase


# ─── User Profile ────────────────────────────────────────────────────────────

def upsert_user_profile(
    user_id: str,
    email: str,
    full_name: str | None = None,
    organization: str | None = None,
) -> dict | None:
    """Create or update the public user profile."""
    supabase = get_supabase()
    data = {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "organization": organization,
    }
    response = (
        supabase.table("users")
        .upsert(data, on_conflict="id")
        .execute()
    )
    return response.data[0] if response.data else None


def get_user_profile(user_id: str) -> dict | None:
    """Fetch the public user profile."""
    supabase = get_supabase()
    response = (
        supabase.table("users")
        .select("*")
        .eq("id", user_id)
        .single()
        .execute()
    )
    return response.data


# ─── Patients ────────────────────────────────────────────────────────────────

def create_patient(
    user_id: str,
    patient_name: str,
    patient_id: str | None = None,
    date_of_birth: date | None = None,
    gender: str | None = None,
) -> dict | None:
    """Create a new patient record."""
    supabase = get_supabase()
    data: dict[str, Any] = {
        "user_id": user_id,
        "patient_name": patient_name,
    }
    if patient_id:
        data["patient_id"] = patient_id
    if date_of_birth:
        data["date_of_birth"] = date_of_birth.isoformat()
    if gender:
        data["gender"] = gender

    response = supabase.table("patients").insert(data).execute()
    return response.data[0] if response.data else None


def list_patients(user_id: str) -> list[dict]:
    """List all patients belonging to a user."""
    supabase = get_supabase()
    response = (
        supabase.table("patients")
        .select("*")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def get_patient(patient_uuid: str) -> dict | None:
    """Fetch a single patient by UUID."""
    supabase = get_supabase()
    response = (
        supabase.table("patients")
        .select("*")
        .eq("id", patient_uuid)
        .single()
        .execute()
    )
    return response.data


# ─── Genome Analyses ─────────────────────────────────────────────────────────

def create_genome_analysis(
    user_id: str,
    patient_id: str,
    genome_id: str,
    species: str,
    fasta_file_url: str | None = None,
) -> dict | None:
    """Create a new genome analysis record."""
    supabase = get_supabase()
    data: dict[str, Any] = {
        "user_id": user_id,
        "patient_id": patient_id,
        "genome_id": genome_id,
        "species": species,
        "status": "pending",
    }
    if fasta_file_url:
        data["fasta_file_url"] = fasta_file_url

    response = supabase.table("genome_analyses").insert(data).execute()
    return response.data[0] if response.data else None


def update_analysis_status(analysis_id: str, status: str) -> dict | None:
    """Update the status of a genome analysis (pending -> processing -> complete -> failed)."""
    supabase = get_supabase()
    response = (
        supabase.table("genome_analyses")
        .update({"status": status})
        .eq("id", analysis_id)
        .execute()
    )
    return response.data[0] if response.data else None


def list_analyses(user_id: str) -> list[dict]:
    """List all genome analyses for a user."""
    supabase = get_supabase()
    response = (
        supabase.table("genome_analyses")
        .select("*, patients(patient_name)")
        .eq("user_id", user_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data or []


def get_analysis(analysis_id: str) -> dict | None:
    """Fetch a single analysis by UUID."""
    supabase = get_supabase()
    response = (
        supabase.table("genome_analyses")
        .select("*, patients(patient_name)")
        .eq("id", analysis_id)
        .single()
        .execute()
    )
    return response.data


# ─── Predictions ─────────────────────────────────────────────────────────────

def save_predictions(
    user_id: str,
    analysis_id: str,
    reports: list[dict],
) -> list[dict]:
    """
    Save a batch of prediction reports for a genome analysis.
    Maps from the report format (DATA_SPEC §6) to the predictions table schema.
    """
    supabase = get_supabase()
    rows = []
    for report in reports:
        rows.append({
            "user_id": user_id,
            "analysis_id": analysis_id,
            "antibiotic": report.get("antibiotic", "unknown"),
            "verdict": report.get("verdict", "nocall"),
            "confidence": report.get("confidence", 0.0),
            "evidence_category": report.get("evidence_category", "iii"),
            "supporting_genes": report.get("supporting_features", []),
            "target_present": report.get("target_present", False),
            "reason": "; ".join(report.get("reasons", [])) or None,
        })

    response = supabase.table("predictions").insert(rows).execute()
    return response.data or []


def get_predictions_for_analysis(analysis_id: str) -> list[dict]:
    """Fetch all predictions for a given analysis."""
    supabase = get_supabase()
    response = (
        supabase.table("predictions")
        .select("*")
        .eq("analysis_id", analysis_id)
        .order("antibiotic")
        .execute()
    )
    return response.data or []
