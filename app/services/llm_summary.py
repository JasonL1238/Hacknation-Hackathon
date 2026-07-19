"""Flag-gated OpenAI plain-language clinician summary (optional Module 03 layer).

Turns the *structured* antibiotic-response report into a short, plain-language
paragraph for a clinician. It is STRICTLY grounded: the model is given only the
predictions already produced by our pipeline and is forbidden from introducing any
new drug, gene, mechanism, or treatment decision. Every summary defers to laboratory
confirmation.

Safety / honesty properties:
- OFF by default. Enabled only when OPENAI_API_KEY is set; GENOME_FIREWALL_LLM=off
  force-disables. So the demo runs identically with no key, and no fabricated text
  ever appears unless a real key is configured.
- Never fabricates on failure: if the `openai` package or key is missing, or the API
  errors, it returns None and the UI simply hides the section.
- Grounding only: the summary restates our own structured output in prose — it is not
  an independent prediction and must not be read as one.
"""
from __future__ import annotations

import json
import os
from typing import Any

_SYSTEM = (
    "You are a careful clinical decision-support summarizer for an antibiotic-"
    "resistance prediction tool. You will be given a JSON list of the tool's own "
    "per-antibiotic predictions for one bacterial isolate. Write a short, plain-"
    "language summary for a clinician.\n"
    "STRICT RULES:\n"
    "1. Use ONLY the information in the JSON. Do NOT mention any antibiotic, gene, "
    "mutation, or mechanism that is not present in it.\n"
    "2. Do NOT make a treatment decision or recommend a specific drug. This is "
    "decision support, not a prescription.\n"
    "3. Group the summary by likely-to-work, likely-to-fail, and no-call. State "
    "no-calls honestly as insufficient/uncertain evidence, not as a failure.\n"
    "4. Keep it to 3-5 sentences, neutral and factual.\n"
    "5. End with exactly: 'Confirm every result with standard laboratory testing "
    "before any clinical decision.'"
)


def is_enabled() -> bool:
    """True only if an OpenAI key is configured and the feature isn't force-disabled."""
    if os.environ.get("GENOME_FIREWALL_LLM", "").strip().lower() in ("0", "false", "off", "no"):
        return False
    return bool(os.environ.get("OPENAI_API_KEY", "").strip())


def _model() -> str:
    return os.environ.get("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini"


def _grounding_payload(results: list[Any]) -> list[dict]:
    """Reduce the AntibioticResult objects to the minimal facts the model may use."""
    payload = []
    for r in results:
        payload.append({
            "antibiotic": getattr(r, "antibiotic", ""),
            "drug_class": getattr(r, "drug_class", ""),
            "prediction": getattr(r, "prediction", ""),
            "confidence": round(float(getattr(r, "confidence", 0.0) or 0.0), 3),
            "evidence_category": getattr(r, "evidence_category", ""),
            "target_gate": getattr(r, "target_gate", ""),
            "supporting_genes": list(getattr(r, "supporting_genes", []) or []),
            "supporting_mutations": list(getattr(r, "supporting_mutations", []) or []),
        })
    return payload


def summarize(results: list[Any], *, species: str = "Staphylococcus aureus") -> str | None:
    """Return a grounded plain-language summary, or None if disabled/unavailable.

    Never raises: any failure (missing package, missing key, API/network error) is
    swallowed and reported as None so the caller hides the section.
    """
    if not is_enabled() or not results:
        return None
    try:
        from openai import OpenAI  # lazy — package is optional
    except ImportError:
        return None

    user = (
        f"Isolate species: {species}\n"
        f"Tool predictions (JSON):\n{json.dumps(_grounding_payload(results), indent=2)}"
    )
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=_model(),
            temperature=0.2,
            max_tokens=350,
            messages=[{"role": "system", "content": _SYSTEM},
                      {"role": "user", "content": user}],
        )
        text = (resp.choices[0].message.content or "").strip()
        return text or None
    except Exception:  # noqa: BLE001 — any API/network failure → hide the section
        return None
