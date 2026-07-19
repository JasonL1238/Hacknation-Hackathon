"""Security-focused tests for Streamlit/Supabase deployment configuration."""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import app.supabase_client as client_module


class SupabaseClientTests(unittest.TestCase):
    def test_missing_credentials_are_not_configured(self) -> None:
        fake_streamlit = SimpleNamespace(session_state={}, secrets={})
        with (
            patch.dict(
                os.environ,
                {"SUPABASE_URL": "", "SUPABASE_KEY": ""},
                clear=False,
            ),
            patch.object(client_module, "st", fake_streamlit),
            patch.object(client_module, "_load_env"),
        ):
            self.assertFalse(client_module.supabase_configured())

    def test_client_is_reused_only_within_one_streamlit_session(self) -> None:
        first_client = object()
        second_client = object()
        factory = Mock(side_effect=[first_client, second_client])
        credentials = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "sb_publishable_example",
        }

        first_visitor = SimpleNamespace(session_state={}, secrets={})
        second_visitor = SimpleNamespace(session_state={}, secrets={})
        with (
            patch.dict(os.environ, credentials, clear=False),
            patch.object(client_module, "create_client", factory),
        ):
            with patch.object(client_module, "st", first_visitor):
                self.assertIs(client_module.get_supabase(), first_client)
                self.assertIs(client_module.get_supabase(), first_client)

            with patch.object(client_module, "st", second_visitor):
                self.assertIs(client_module.get_supabase(), second_client)

        self.assertEqual(factory.call_count, 2)

    def test_secret_key_is_rejected_before_client_creation(self) -> None:
        fake_streamlit = SimpleNamespace(session_state={}, secrets={})
        credentials = {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "sb_secret_do_not_use",
        }
        with (
            patch.dict(os.environ, credentials, clear=False),
            patch.object(client_module, "st", fake_streamlit),
            patch.object(client_module, "create_client") as factory,
        ):
            with self.assertRaisesRegex(RuntimeError, "publishable/anon"):
                client_module.get_supabase()

        factory.assert_not_called()

    def test_clear_client_removes_only_supabase_session_keys(self) -> None:
        fake_streamlit = SimpleNamespace(
            session_state={
                "_supabase_client": object(),
                "_supabase_client_config": ("url", "hash"),
                "unrelated": "keep",
            },
            secrets={},
        )
        with patch.object(client_module, "st", fake_streamlit):
            client_module.clear_supabase_client()

        self.assertEqual(fake_streamlit.session_state, {"unrelated": "keep"})


if __name__ == "__main__":
    unittest.main()
