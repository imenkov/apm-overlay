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
        self,
        library: Path,
        name: str,
        description: str = "",
        dependency: str = "org/pkg",
        dependencies: list[str] | None = None,
    ) -> Path:
        overlay = library / name
        overlay.mkdir(parents=True)
        dependencies = dependencies or [dependency]
        dependency_lines = "".join(f"    - {item}\n" for item in dependencies)
        manifest = (
            f"name: {name}\n"
            f"description: {description}\n"
            "dependencies:\n"
            "  apm:\n"
            f"{dependency_lines}"
            "  mcp: []\n"
        )
        (overlay / "apm.yml").write_text(manifest)
        return overlay

    def create_fake_apm(self) -> Path:
        bin_dir = self.root / "bin"
        bin_dir.mkdir(exist_ok=True)
        apm = bin_dir / "apm"
        apm.write_text(
            """#!/usr/bin/env python3
import os
import sys
from pathlib import Path

import yaml

args = sys.argv[1:]
if not args or args[0] != "install":
    raise SystemExit(0)

scope = Path.home() / ".apm" if "-g" in args else Path.cwd()
scope.mkdir(parents=True, exist_ok=True)
packages = []
skip_next = False
for arg in args[1:]:
    if skip_next:
        skip_next = False
    elif arg in {"--only", "--target"}:
        skip_next = True
    elif not arg.startswith("-"):
        packages.append(arg)

accept_count = int(os.environ.get("FAKE_APM_ACCEPT_COUNT", len(packages)))
accepted = packages[:accept_count]
if os.environ.get("FAKE_APM_CANONICALIZE"):
    accepted = [
        package.removeprefix("https://github.com/").removesuffix(".git").lower()
        for package in accepted
    ]
locked = accepted[:int(os.environ.get("FAKE_APM_LOCK_COUNT", len(accepted)))]
(scope / "apm.yml").write_text(yaml.safe_dump({
    "dependencies": {"apm": accepted, "mcp": []}
}, sort_keys=False))
(scope / "apm.lock.yaml").write_text(yaml.safe_dump({
    "lockfile_version": "1",
    "dependencies": [{"repo_url": package} for package in locked],
}, sort_keys=False))
raise SystemExit(int(os.environ.get("FAKE_APM_EXIT_CODE", "0")))
"""
        )
        apm.chmod(0o755)
        return bin_dir

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

        bin_dir = self.create_fake_apm()

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

    def test_partial_success_records_only_accepted_packages_and_fails(self):
        library = self.root / "library"
        self.create_overlay(
            library,
            "partial",
            dependencies=["https://github.com/Org/Accepted.git", "org/skipped"],
        )
        bin_dir = self.create_fake_apm()
        path = os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")])

        for scope_global in (False, True):
            with self.subTest(scope_global=scope_global):
                project = self.root / ("global-project" if scope_global else "project")
                project.mkdir()
                args = ["install", "partial"]
                if scope_global:
                    args.append("-g")
                result = self.run_cli(
                    *args,
                    cwd=project,
                    env={
                        "APM_OVERLAYS_DIRS": str(library),
                        "PATH": path,
                        "FAKE_APM_ACCEPT_COUNT": "1",
                        "FAKE_APM_CANONICALIZE": "1",
                    },
                )

                self.assertNotEqual(result.returncode, 0)
                self.assertIn("skipped requested packages: org/skipped", result.stderr)
                self.assertIn("recorded as an incomplete overlay", result.stderr)

                state_path = (
                    self.home / ".apm" / "overlays.state.json"
                    if scope_global
                    else project / "apm.overlays.json"
                )
                state = json.loads(state_path.read_text())
                self.assertEqual(state["partial"]["added_apm"], ["org/accepted"])
                self.assertFalse(state["partial"]["complete"])
                self.assertEqual(state["partial"]["incomplete_apm"], ["org/skipped"])

                status_args = ["status"]
                if scope_global:
                    status_args.append("-g")
                status = self.run_cli(*status_args, cwd=project)
                self.assertEqual(status.returncode, 0, status.stderr)
                self.assertIn("INCOMPLETE", status.stdout)
                self.assertIn("+ apm: org/accepted", status.stdout)
                self.assertIn("! skipped apm: org/skipped", status.stdout)

                uninstall_args = ["uninstall", "partial", "--dry-run"]
                if scope_global:
                    uninstall_args.append("-g")
                uninstall = self.run_cli(
                    *uninstall_args,
                    cwd=project,
                    env={"PATH": path},
                )
                self.assertEqual(uninstall.returncode, 0, uninstall.stderr)
                self.assertIn("apm uninstall", uninstall.stdout)
                self.assertIn("org/accepted", uninstall.stdout)
                self.assertNotIn("org/skipped", uninstall.stdout)

                if scope_global:
                    state_path.unlink()

    def test_manifest_addition_missing_from_lock_is_incomplete(self):
        library = self.root / "library"
        self.create_overlay(library, "unlocked", dependency="org/accepted")
        project = self.root / "project"
        project.mkdir()
        bin_dir = self.create_fake_apm()

        result = self.run_cli(
            "install",
            "unlocked",
            cwd=project,
            env={
                "APM_OVERLAYS_DIRS": str(library),
                "PATH": os.pathsep.join([str(bin_dir), os.environ.get("PATH", "")]),
                "FAKE_APM_LOCK_COUNT": "0",
            },
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("lockfile is missing accepted packages: org/accepted", result.stderr)
        state = json.loads((project / "apm.overlays.json").read_text())
        self.assertEqual(state["unlocked"]["added_apm"], ["org/accepted"])
        self.assertFalse(state["unlocked"]["complete"])

    def test_dry_run_does_not_require_or_modify_apm_state(self):
        library = self.root / "library"
        self.create_overlay(
            library,
            "preview",
            dependencies=["org/first", "org/second"],
        )
        project = self.root / "project"
        project.mkdir()

        result = self.run_cli(
            "install",
            "preview",
            "--dry-run",
            cwd=project,
            env={"APM_OVERLAYS_DIRS": str(library), "PATH": ""},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "[dry-run] apm install --only apm org/first org/second",
            result.stdout,
        )
        self.assertFalse((project / "apm.yml").exists())
        self.assertFalse((project / "apm.lock.yaml").exists())
        self.assertFalse((project / "apm.overlays.json").exists())

    def test_install_commands_disable_transitive_mcp_configuration(self):
        library = self.root / "library"
        self.create_overlay(library, "safe", dependency="org/pkg")
        project = self.root / "project"
        project.mkdir()
        env = {"APM_OVERLAYS_DIRS": str(library), "PATH": ""}

        cases = (
            ((), "apm install --only apm org/pkg"),
            (("-g",), "apm install --only apm -g org/pkg"),
            (
                ("--target", "copilot"),
                "apm install --only apm --target copilot org/pkg",
            ),
            (
                ("-g", "--target", "copilot"),
                "apm install --only apm -g --target copilot org/pkg",
            ),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                result = self.run_cli(
                    "install",
                    "safe",
                    *options,
                    "--dry-run",
                    cwd=project,
                    env=env,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"[dry-run] {expected}", result.stdout)

    def test_uninstall_does_not_forward_unsupported_target_option(self):
        project = self.root / "project"
        project.mkdir()
        entry = {
            "overlay": {
                "added_apm": ["org/pkg"],
                "added_mcp": [],
                "applied_at": "2026-01-01T00:00:00+00:00",
            }
        }
        (project / "apm.overlays.json").write_text(json.dumps(entry))
        global_state = self.home / ".apm" / "overlays.state.json"
        global_state.parent.mkdir()
        global_state.write_text(json.dumps(entry))

        cases = (
            ((), "apm uninstall org/pkg"),
            (("-g",), "apm uninstall -g org/pkg"),
        )
        for options, expected in cases:
            with self.subTest(options=options):
                result = self.run_cli(
                    "uninstall",
                    "overlay",
                    *options,
                    "--target",
                    "copilot",
                    "--dry-run",
                    cwd=project,
                    env={"PATH": ""},
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn(f"[dry-run] {expected}", result.stdout)
                self.assertNotIn("--target", result.stdout)


if __name__ == "__main__":
    unittest.main()
