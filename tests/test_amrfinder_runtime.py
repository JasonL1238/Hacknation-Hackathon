"""Tests for lazy AMRFinderPlus database provisioning."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from genome_firewall import annotate


class AmrFinderRuntimeTests(unittest.TestCase):
    def test_existing_database_does_not_run_update(self) -> None:
        with (
            patch.object(annotate, "_installed_db_version", return_value="2026-05-15.1"),
            patch.object(annotate.subprocess, "run") as run,
        ):
            self.assertEqual(annotate.amrfinder_db_version(), "2026-05-15.1")
        run.assert_not_called()

    def test_missing_database_is_provisioned_in_runtime_storage(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch.dict(
                    os.environ,
                    {
                        "BIOSHIELD_AMRFINDER_DATA_ROOT": directory,
                        "AMRFINDER_DB": "",
                    },
                    clear=False,
                ),
                patch.object(
                    annotate,
                    "_installed_db_version",
                    side_effect=[
                        RuntimeError("missing"),
                        RuntimeError("missing"),
                        "2026-05-15.1",
                    ],
                ),
                patch.object(annotate, "amrfinder_command", return_value=["amrfinder"]),
                patch.object(
                    annotate,
                    "amrfinder_update_command",
                    return_value=["amrfinder_update"],
                ),
                patch.object(
                    annotate.subprocess,
                    "run",
                    return_value=SimpleNamespace(returncode=0, stdout="", stderr=""),
                ) as run,
            ):
                version = annotate.amrfinder_db_version()
                selected_database = os.environ["AMRFINDER_DB"]

            self.assertEqual(version, "2026-05-15.1")
            run.assert_called_once_with(
                ["amrfinder_update", "--database", directory],
                capture_output=True,
                text=True,
                timeout=900,
            )
            self.assertEqual(selected_database, str(Path(directory)))


if __name__ == "__main__":
    unittest.main()
