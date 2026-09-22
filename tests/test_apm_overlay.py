from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
CLI = REPO_ROOT / "tools" / "apm-overlay"


class ApmOverlayCliTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.home = self.root / "home"
        self.home.mkdir()

    def tearDown(self):
        self.temp_dir.cleanup()

    def create_overlay(
        self, library: Path, name: str, description: str = "", dependency: str = "org/pkg"
    ) -> Path:
        overlay = library / name
        overlay.mkdir(parents=True)
        manifest = (
            f"name: {name}\n"
            f"description: {description}\n"
            "dependencies:\n"
            "  apm:\n"
            f"    - {dependency}\n"
            "  mcp: []\n"
        )
        (overlay / "apm.yml").write_text(manifest)
        return overlay

    def run_cli(self, *args: str, cwd: Path | None = None, env: dict | None = None):
        process_env = os.environ.copy()
        process_env["HOME"] = str(self.home)
        process_env["PYTHONPATH"] = os.pathsep.join(path for path in sys.path if path)
        process_env.pop("APM_OVERLAYS_DIRS", None)
        process_env.pop("APM_OVERLAYS_DIR", None)
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            cwd=cwd or self.root,
            env=process_env,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_plural_env_precedes_legacy_and_empty_plural_falls_back(self):
        plural_library = self.home / "plural"
        legacy_library = self.root / "legacy"
        default_library = self.home / ".apm" / "overlays"
        self.create_overlay(plural_library, "plural-only")
        self.create_overlay(legacy_library, "legacy-only")
        self.create_overlay(default_library, "default-only")

        result = self.run_cli(
            "list",
            env={
                "APM_OVERLAYS_DIRS": os.pathsep.join(
                    ["~/plural", "", str(plural_library)]
                ),
                "APM_OVERLAYS_DIR": str(legacy_library),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("plural-only"), 1)
        self.assertNotIn("legacy-only", result.stdout)

        fallback = self.run_cli(
            "list",
            env={
                "APM_OVERLAYS_DIRS": os.pathsep,
                "APM_OVERLAYS_DIR": str(legacy_library),
            },
        )
        self.assertEqual(fallback.returncode, 0, fallback.stderr)
        self.assertIn("legacy-only", fallback.stdout)
        self.assertNotIn("plural-only", fallback.stdout)

        default = self.run_cli("list")
        self.assertEqual(default.returncode, 0, default.stderr)
        self.assertIn("default-only", default.stdout)
        self.assertNotIn("legacy-only", default.stdout)

    def test_list_aggregates_sources_and_marks_duplicate_names_ambiguous(self):
        first = self.root / "first"
        second = self.root / "second"
        self.create_overlay(first, "shared", "first copy")
        self.create_overlay(second, "shared", "second copy")
        self.create_overlay(second, "unique", "only here")

        result = self.run_cli(
            "list",
            env={"APM_OVERLAYS_DIRS": os.pathsep.join([str(first), str(second)])},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(f"[source: {first}]", result.stdout)
        self.assertIn(f"[source: {second}]", result.stdout)
        self.assertEqual(result.stdout.count("[AMBIGUOUS: 2 matches]"), 2)
        self.assertIn("unique — only here", result.stdout)

    def test_show_resolves_a_unique_match_across_all_libraries(self):
        first = self.root / "first"
        second = self.root / "second"
        first.mkdir()
        overlay = self.create_overlay(second, "unique", "resolved from second")

        result = self.run_cli(
            "show",
            "unique",
            env={"APM_OVERLAYS_DIRS": os.pathsep.join([str(first), str(second)])},
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, (overlay / "apm.yml").read_text())

    def test_show_and_install_reject_ambiguous_names_with_all_matches(self):
        first = self.root / "first"
        second = self.root / "second"
        first_overlay = self.create_overlay(first, "shared")
        second_overlay = self.create_overlay(second, "shared")
        env = {"APM_OVERLAYS_DIRS": os.pathsep.join([str(first), str(second)])}

        for command in (("show", "shared"), ("install", "shared", "--dry-run")):
            with self.subTest(command=command):
                result = self.run_cli(*command, env=env)
                output = result.stdout + result.stderr
                self.assertNotEqual(result.returncode, 0)
                self.assertIn("is ambiguous; found 2 matches", output)
                self.assertIn(str(first_overlay.resolve()), output)
                self.assertIn(str(second_overlay.resolve()), output)

    def test_install_records_resolved_source_and_status_reads_legacy_state(self):
        library = self.root / "library"
        overlay = self.create_overlay(library, "unique")
        project = self.root / "project"
        project.mkdir()
        (project / "apm.yml").write_text("dependencies:\n  apm: []\n  mcp: []\n")

        bin_dir = self.root / "bin"
        bin_dir.mkdir()
        apm = bin_dir / "apm"
        apm.write_text("#!/bin/sh\nexit 0\n")
        apm.chmod(0o755)

        result = self.run_cli(
            "install",
            "unique",
            cwd=project,
            env={
                "APM_OVERLAYS_DIRS": str(library),
                "PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]),
            },
        )
        self.assertEqual(result.returncode, 0, result.stderr)

        state_path = project / "apm.overlays.json"
        state = json.loads(state_path.read_text())
        self.assertEqual(state["unique"]["source"], str(overlay.resolve()))

        state["legacy"] = {
            "added_apm": ["org/legacy"],
            "added_mcp": [],
            "applied_at": "2026-01-01T00:00:00+00:00",
        }
        state_path.write_text(json.dumps(state))
        legacy_uninstall = self.run_cli(
            "uninstall",
            "legacy",
            "--dry-run",
            cwd=project,
            env={"PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])},
        )
        self.assertEqual(legacy_uninstall.returncode, 0, legacy_uninstall.stderr)
        self.assertIn("[dry-run] apm uninstall org/legacy", legacy_uninstall.stdout)


if __name__ == "__main__":
    unittest.main()
