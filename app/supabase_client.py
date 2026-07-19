"""Supabase configuration and per-visitor client initialization.

Supabase clients contain mutable authentication state. A process-wide cached
client is unsafe in a public Streamlit app because many visitors share the same
Python process. This module stores one client in each visitor's session instead.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os

import streamlit as st
from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

_CLIENT_KEY = "_supabase_client"
_CONFIG_KEY = "_supabase_client_config"


def _load_env() -> None:
    """Load a local .env file when python-dotenv is available."""

    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass


def get_setting(name: str, default: str = "") -> str:
    """Read a setting from the environment or top-level Streamlit secrets."""

    _load_env()
    value = os.getenv(name)
    if value is not None:
        return str(value).strip()

    try:
        value = st.secrets.get(name, default)
    except (FileNotFoundError, KeyError):
        value = default
    return str(value).strip()


def supabase_configured() -> bool:
    return bool(get_setting("SUPABASE_URL") and get_setting("SUPABASE_KEY"))


def _jwt_role(key: str) -> str | None:
    """Read an unverified role claim only to catch accidental privileged-key use."""

    try:
        payload = key.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
        return str(json.loads(decoded).get("role", "")) or None
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return None


def _validate_public_key(key: str) -> None:
    if key.startswith("sb_secret_") or _jwt_role(key) == "service_role":
        raise RuntimeError(
            "SUPABASE_KEY must be the publishable/anon key, not a secret or "
            "service-role key. Never expose a privileged Supabase key in a web app."
        )


def get_supabase() -> Client:
    """Return a Supabase client isolated to the current Streamlit visitor."""

    url = get_setting("SUPABASE_URL")
    key = get_setting("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set. Add them to Streamlit "
            "Secrets or copy .env.example to .env for local use."
        )
    _validate_public_key(key)

    signature = (url, hashlib.sha256(key.encode("utf-8")).hexdigest())
    if st.session_state.get(_CONFIG_KEY) == signature:
        client = st.session_state.get(_CLIENT_KEY)
        if client is not None:
            return client

    # Streamlit session state is tied to a WebSocket and can reset after a full
    # email-link redirect. The implicit flow lets Supabase confirm the account
    # before redirecting; the visitor then signs in normally. Social OAuth and
    # self-service recovery are intentionally not offered by this auth-only app.
    options = SyncClientOptions(flow_type="implicit", persist_session=True)
    client = create_client(url, key, options=options)
    st.session_state[_CLIENT_KEY] = client
    st.session_state[_CONFIG_KEY] = signature
    return client


def clear_supabase_client() -> None:
    """Discard auth state held by the current visitor's client."""

    st.session_state.pop(_CLIENT_KEY, None)
    st.session_state.pop(_CONFIG_KEY, None)
