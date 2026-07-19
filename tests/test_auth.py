"""Authentication behavior that does not require a live Supabase project."""

from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import patch

import app.auth as auth


class AuthTests(unittest.TestCase):
    def test_demo_session_is_marked_as_guest(self) -> None:
        fake_streamlit = SimpleNamespace(session_state={})
        with (
            patch.object(auth, "st", fake_streamlit),
            patch.object(auth, "demo_mode_available", return_value=True),
        ):
            auth.enter_guest_mode()
            self.assertTrue(auth.is_authenticated())
            self.assertTrue(auth.is_guest())
            self.assertEqual(auth.get_current_user()["id"], "guest")

    def test_dns_failure_has_actionable_message(self) -> None:
        error = OSError(8, "nodename nor servname provided, or not known")
        message = auth._friendly_auth_error(error)
        self.assertIn("SUPABASE_URL", message)
        self.assertIn("Project URL", message)


if __name__ == "__main__":
    unittest.main()
