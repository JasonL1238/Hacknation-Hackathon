"""
Supabase client initialization for BioShield AI.

Reads SUPABASE_URL and SUPABASE_KEY from environment variables or .env file.
"""

from __future__ import annotations

import os
from functools import lru_cache

from supabase import create_client, Client


def _load_env() -> None:
    """Load .env file if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass


@lru_cache(maxsize=1)
def get_supabase() -> Client:
    """Return a singleton Supabase client.

    Uses the PKCE OAuth flow so social logins (Google) redirect back with a
    `?code=` query parameter that a server-side Streamlit app can read — the
    default implicit flow returns tokens in the URL fragment, which the server
    never sees. The client is a process-lived singleton, so the PKCE code
    verifier persists across the OAuth redirect.
    """
    _load_env()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY must be set. "
            "Copy .env.example to .env and fill in your Supabase project credentials."
        )
    # supabase-py defaults flow_type to "pkce", which is what we need so Google
    # OAuth returns a readable ?code= param. We intentionally pass no ClientOptions:
    # the base ClientOptions lacks the `storage` field the sync client requires,
    # so the library must build its own SyncClientOptions internally.
    return create_client(url, key)
