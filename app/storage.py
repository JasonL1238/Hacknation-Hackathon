"""
File storage module for BioShield AI.

Uploads FASTA files to Supabase Storage, organized by user ID.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.supabase_client import get_supabase

BUCKET_NAME = "genome-files"


def upload_fasta(user_id: str, file_bytes: bytes, original_filename: str) -> str | None:
    """
    Upload a FASTA file to Supabase Storage.

    Files are stored as: {user_id}/{uuid}_{original_filename}
    Returns the public URL of the uploaded file, or None on failure.
    """
    supabase = get_supabase()

    # Generate a unique path to avoid collisions
    file_id = uuid.uuid4().hex[:12]
    safe_name = Path(original_filename).name  # strip any path components
    storage_path = f"{user_id}/{file_id}_{safe_name}"

    try:
        supabase.storage.from_(BUCKET_NAME).upload(
            path=storage_path,
            file=file_bytes,
            file_options={"content-type": "application/octet-stream"},
        )
        # Get public URL
        url_response = supabase.storage.from_(BUCKET_NAME).get_public_url(storage_path)
        return url_response
    except Exception:
        return None


def delete_fasta(file_url: str) -> bool:
    """Delete a file from storage given its URL. Returns True on success."""
    supabase = get_supabase()
    try:
        # Extract path from URL (everything after /object/public/{bucket}/)
        marker = f"/object/public/{BUCKET_NAME}/"
        if marker in file_url:
            path = file_url.split(marker, 1)[1]
        else:
            return False
        supabase.storage.from_(BUCKET_NAME).remove([path])
        return True
    except Exception:
        return False
