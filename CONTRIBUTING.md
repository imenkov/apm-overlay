# Contributing to apm-overlay

Thanks for your interest in contributing! This is a personal, community-run
open-source project (see the disclaimer in the [README](./README.md)).
Contributions of all kinds are welcome: bug reports, feature ideas, docs, and
code.

## Before you start

- For anything non-trivial, please open an issue first so we can discuss the
  approach before you invest time in a pull request.
- Be respectful and constructive — see the
  [Code of Conduct](./CODE_OF_CONDUCT.md).
- By contributing, you agree that your contributions are licensed under the
  project's [MIT License](./LICENSE).

## Development setup

Prerequisites: `apm` >= 0.16, Python 3.9+.

```bash
git clone https://github.com/imenkov/apm-overlay.git
cd apm-overlay
apm install                         # installs the project's apm dependencies
./tools/local-install.sh            # creates a .venv and a launcher
```

The tool is a single Python file (`tools/apm-overlay`) with two dependencies,
`click` and `pyyaml`. To run it directly during development:

```bash
python3 -m venv .venv
.venv/bin/pip install click pyyaml
.venv/bin/python tools/apm-overlay --help
```

## Project layout

| Path | Role |
|---|---|
| `tools/apm-overlay` | Single-file Python CLI (Click + PyYAML). |
| `tools/local-install.sh` | Local installer (venv + launcher). |
| `install.sh` | Bootstrap installer used via `curl ... \| sh`. |
| `overlays/` | Example overlay library (each subdir is an apm project). |
| `docs/` | Architecture and usage reference. |

See [`docs/architecture.md`](./docs/architecture.md) for the design rationale
and code map.

## Making changes

1. Create a branch off `main`.
2. Keep changes focused and surgical; match the existing style.
3. Update the docs (`README.md`, `docs/usage.md`, `docs/architecture.md`) when
   behavior or flags change.
4. Smoke-test your change:
   ```bash
   .venv/bin/python tools/apm-overlay --version
   .venv/bin/python tools/apm-overlay --help
   .venv/bin/python tools/apm-overlay list
   ```
   Use `--dry-run` to exercise `install` / `uninstall` paths without touching
   real apm state.

## Commit messages

This repo follows [Conventional Commits](https://www.conventionalcommits.org/),
e.g. `feat:`, `fix:`, `docs:`, `chore:`. Keep the subject line concise and
explain the *why* in the body when it isn't obvious.

## Pull requests

- Reference the issue your PR addresses.
- Describe what changed and how you verified it.
- Keep unrelated changes out of the PR.

Thanks again for helping improve apm-overlay!
