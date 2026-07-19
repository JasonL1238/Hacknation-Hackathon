"""Best-effort extraction of a patient's name and MRN from an uploaded PDF.

Heuristic only — the doctor always reviews and confirms the extracted values
before a patient record is created. Nothing here is authoritative.
"""

from __future__ import annotations

import io
import re

_NAME_PATTERNS = [
    r"patient\s*name\s*[:\-]\s*(.+)",
    r"\bname\s*[:\-]\s*(.+)",
    r"patient\s*[:\-]\s*(.+)",
]
_MRN_PATTERNS = [
    r"(?:mrn|medical\s*record\s*(?:number|no\.?|#)?)\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]{2,})",
    r"patient\s*(?:id|identifier|number|no\.?|#)\s*[:#\-]?\s*([A-Za-z0-9][A-Za-z0-9\-]{2,})",
]

# Stop a captured name before a label that often follows it on the same line.
_NAME_STOP = re.compile(
    r"\s+(?:mrn|dob|date\s*of\s*birth|patient\s*id|sex|gender|age)\b", re.IGNORECASE
)


def _extract_text(data: bytes) -> str:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    parts = []
    for page in reader.pages[:5]:  # patient headers live on the first page(s)
        try:
            parts.append(page.extract_text() or "")
        except Exception:  # noqa: BLE001
            continue
    return "\n".join(parts)


def _first_match(patterns: list[str], text: str) -> str | None:
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m:
            val = m.group(1).strip()
            if val:
                return val
    return None


def parse_patient_pdf(data: bytes) -> dict:
    """Return {"name": str|None, "mrn": str|None, "ok": bool, "error": str|None}."""
    try:
        text = _extract_text(data)
    except Exception as e:  # noqa: BLE001
        return {"name": None, "mrn": None, "ok": False, "error": str(e)}

    name = _first_match(_NAME_PATTERNS, text)
    if name:
        name = _NAME_STOP.split(name)[0].strip(" .,:-")
        # Keep it to a sensible person-name length.
        name = name[:80] if name else None

    mrn = _first_match(_MRN_PATTERNS, text)
    return {"name": name or None, "mrn": mrn or None, "ok": True, "error": None}
