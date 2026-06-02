# Architecture

This document explains how `apm-overlay` is structured, the contracts it
relies on, and the design decisions behind it. If you want to merge this
feature into apm itself, this is the document to read first.

## Design goals

1. **Reversible**: applying an overlay must be cleanly undoable, even after a
   crash, an interrupted install, or a forgotten session.
2. **Composable**: multiple overlays may be active at the same scope at once
   without stomping on each other.
3. **apm-native**: file formats, command verbs, flags, and storage locations
   mirror apm's conventions so the tool feels like an extension and can be
   merged upstream with minimal change.
4. **Non-invasive**: never reimplements anything apm already does. The tool
   shells out to `apm install` / `apm uninstall` and lets apm own resolution,
   deployment, lockfile management, and primitive integration.
5. **Predictable**: every state change is preceded by a clearly-printed
   command (with `-v`) and previewable (with `--dry-run`). Failed apm
   invocations leave state files untouched.

## Non-goals (v1)

- No MCP install support (apm has different CLI for `--mcp` install).
- No conflict resolution between baseline and overlay versions — apm's
  resolver decides; we only handle additions and removals.
- No support for editing overlays while they are active (uninstall first).
- No bundling or distribution of overlays (overlays are local dirs, optionally
  versioned in git like any other repo).

## High-level architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                            User CLI                                 │
│         apm-overlay {list, show, status, install, uninstall}        │
└─────────────────────────────────────────────────────────────────────┘
                │                                  │
                ▼                                  ▼
   ┌────────────────────────┐         ┌────────────────────────────┐
   │  Overlay library       │         │  apm CLI (subprocess)      │
   │  $APM_OVERLAYS_DIR     │         │  apm install / uninstall   │
   │  └─ <name>/apm.yml     │         │  -g for user scope         │
   └────────────────────────┘         └────────────────────────────┘
                │                                  │
                │ read deps                        │ mutates
                ▼                                  ▼
   ┌────────────────────────┐         ┌────────────────────────────┐
   │  State files           │  ◀──┐   │  apm-owned state           │
   │  per-scope JSON        │     │   │  - apm.yml                 │
   │  records what each     │     │   │  - apm.lock.yaml           │
   │  overlay actually      │     │   │  - apm_modules/            │
   │  added                 │     │   │  - deployed primitives     │
   └────────────────────────┘     │   │    (.agents, .claude, ...) │
                                  │   └────────────────────────────┘
                                  │
                                  └── source of truth for "undo"
```

`apm-overlay` only writes to its own state files and shells out to apm; apm
owns everything else.

## Components

### 1. Overlay library

Discovered via the `APM_OVERLAYS_DIR` environment variable (default
`~/.apm/overlays/`). Each subdirectory whose root contains `apm.yml` is
considered an overlay. The overlay's `name` for CLI purposes is the directory
name.

The overlay's `apm.yml` is a standard apm project manifest. The tool only
reads:

| Field | Use |
|---|---|
| `description` | Shown in `apm-overlay list` |
| `dependencies.apm` | Packages to install/uninstall |
| `dependencies.mcp` | Detected and warned about (not yet installed) |

Any other apm fields (`name`, `version`, `targets`, `scripts`, etc.) are
preserved untouched so the overlay can also be used as a standalone apm
project (e.g., to test it via `apm install` inside the overlay dir).

### 2. State files

`apm-overlay` records exactly what an overlay added. This is the **single
source of truth for undo**.

| Scope | Path |
|---|---|
| Global | `~/.apm/overlays.state.json` |
| Project | `<cwd>/apm.overlays.json` |

Format:

```json
{
  "<overlay-name>": {
    "added_apm": ["org/repo", "org/other-repo@v1"],
    "added_mcp": [],
    "applied_at": "2026-06-02T12:39:48+00:00"
  },
  ...
}
```

Writes are atomic (write to `*.tmp` → `rename`) so a crash during save never
leaves a corrupt file. The file is small JSON; no schema migration needed for
v1.

### 3. apm bridge

A single helper, `run_apm(args, dry_run, verbose)`, builds and runs the
`apm` command. With `--dry-run` the command is printed but not executed
(state files are also untouched). With `-v` the resolved command is echoed
before running. If apm exits non-zero, the state file is **not** updated, so
re-running `install` or `uninstall` after a transient failure is safe.

## Data flow

### `install <name> [-g]`

```
1. Resolve overlay dir from $APM_OVERLAYS_DIR / <name>
2. Parse overlay's apm.yml → set O = dependencies.apm
3. Reject if state file already has <name> (no double-apply)
4. Parse active apm.yml (cwd or ~/.apm/) → set A
5. to_install = O − A             # never re-add what baseline already has
6. apm install [-g] <to_install...>
7. On success: state[name] = { added_apm: to_install, ..., applied_at: ts }
   On failure: do NOT touch state
```

Key invariant: `state[name].added_apm` always reflects exactly which packages
were appended to apm.yml by THIS overlay application.

### `uninstall <name> [-g]`

```
1. Look up state[name]; reject if missing
2. claimed_by_others = ⋃ over state[k != name] of added_apm
3. to_remove = state[name].added_apm − claimed_by_others
4. (Inform user about packages kept because another overlay still claims them)
5. apm uninstall [-g] <to_remove...>
6. On success: delete state[name]
   On failure: state preserved → user can retry or investigate
```

Key invariant: we never uninstall a package the overlay did not add, and
never uninstall a package another active overlay still needs.

## Why these decisions

| Decision | Rationale |
|---|---|
| Overlay = full apm project dir (not a YAML fragment) | Uses apm's existing scaffolder (`apm plugin init`), can be tested standalone, future-proof if apm adopts cascading-meta-package installs (it would become the actual implementation). |
| State file as source of truth (not "diff against baseline at uninstall time") | Baseline can change while overlay is active. Recording additions at install time makes undo deterministic regardless of subsequent changes. |
| Atomic JSON writes | Cheap insurance against crashes. The "tmp+rename" pattern is the standard Unix-safe save. |
| `-g/--global` exactly mirrors apm | Muscle memory transfers; eventual `apm overlay` subcommand would not change UX. |
| No MCP installs in v1 | `apm install --mcp` requires different argument shape and metadata; deserves its own design pass. The tool warns rather than silently skipping. |
| Reject double-apply | Prevents the state file from drifting away from reality (would be ambiguous what to uninstall). Force-reapply was deliberately omitted in v1. |
| Refuse to update state on apm failure | Keeps state consistent with reality; user can always re-run the command without orphaning records. |

## Failure modes & guarantees

| Failure | Behavior |
|---|---|
| Overlay file missing | Clear error before any side effect. |
| apm install fails mid-way | apm rolls back its own changes per its design; our state file is untouched, so user can re-run `apm-overlay install`. |
| apm uninstall fails mid-way | State entry preserved → user can re-run, investigate, or manually `apm uninstall` and then edit state. |
| State file corrupted | `apm-overlay status/install/uninstall` errors clearly with the parse error and file path. Manual fix: delete the file (loses overlay tracking; apm-owned state is unaffected). |
| Two overlays add the same package | Both record it. Uninstalling one keeps it (still claimed). Uninstalling both removes it. |
| Package added by overlay is also in baseline | Not added (set difference) and not recorded → uninstall is a no-op for that package. Baseline is preserved. |

## Integration with apm conventions

| apm convention | apm-overlay choice |
|---|---|
| `~/.apm/` for global state | `~/.apm/overlays.state.json` lives next to `marketplaces.json`, `config.json` |
| `apm.yml` + `apm.lock.yaml` at project root | `apm.overlays.json` placed alongside |
| `-g/--global`, `--dry-run`, `-v/--verbose` | Same flags, same semantics |
| Click-based CLI groups + subcommands | Same library |
| Manifest = YAML, state = JSON | Same split |
| Plugin = directory with `apm.yml` (+ optional `plugin.json`) | Overlays are exactly that |

## Path to "merge into apm"

If apm gains a first-class `apm overlay` subcommand, this design transfers
cleanly:

1. **Verbs and flags** are already a 1:1 mapping (`apm-overlay install` →
   `apm overlay install`).
2. **File formats** are already apm-native (overlays are apm projects; state
   is a simple JSON dict that can be moved into apm's state manager).
3. **No CLI plugins API needed today** — apm currently has no general
   extension point; once one exists, this tool can be re-implemented as a
   plugin without changing its surface.
4. **Cascading transitive install of a local apm package would supersede the
   tool entirely**: an overlay is literally a meta-package; if `apm install
   ./overlay-dir` recursively installed `dependencies.apm` and `apm uninstall`
   cascade-removed orphaned transitive deps, the tool would no longer be
   necessary. Until then, this sidecar bridges the gap.

## Code map

| File | Role |
|---|---|
| `tools/apm-overlay` | Single-file Python entrypoint (Click + PyYAML). |
| `overlays/` | The overlay library (directories created by `apm plugin init`). |
| `~/.apm/overlays.state.json` | Auto-managed global-scope state. |
| `<project>/apm.overlays.json` | Auto-managed project-scope state. |

The script has four logical sections, in order:

1. **Paths** — `overlays_dir()`, `state_file()`, `active_apm_yml()`.
2. **IO helpers** — `load_yaml`, `load_state`, `save_state` (atomic write).
3. **Overlay resolution** — `overlay_path`, `extract_deps` (normalizes deps
   to deduped string lists).
4. **CLI** — Click group with `list`, `show`, `status`, `install`,
   `uninstall`.

All apm invocations go through a single `run_apm` helper that handles
`--dry-run` printing and `-v` echoing.
