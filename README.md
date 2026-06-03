# apm-overlay

> Stackable, reversible overlays of [apm](https://github.com/microsoft/apm) packages — globally or per project.

`apm-overlay` lets you keep a small, hand-curated **baseline** of apm packages
in your project (or user scope) and temporarily layer task-specific
**overlays** on top — then cleanly undo them when the task is done.

It is a thin sidecar around stock `apm install` / `apm uninstall`. It does not
fork or shadow apm; it shells out to it. An "overlay" is just a regular apm
project directory whose `dependencies` list is what gets layered.

## Why

The native apm workflow has one `apm.yml` per scope. Adding a task-specific
package mutates that manifest and your lockfile, and remembering exactly what
to remove afterwards is a chore. `apm-overlay`:

- Treats a set of packages as a **named, reusable unit** (the overlay).
- Records which packages each overlay actually added (state file).
- Removes **only those packages** on uninstall — never the baseline, never
  packages another active overlay still claims.
- Supports both **global** (`~/.apm/`) and **project** scopes with identical
  ergonomics.

## Documents

| Doc | Read when |
|---|---|
| [README.md](./README.md) (this file) | First touch, install, 30-second tour |
| [architecture.md](./docs/architecture.md) | You want to know how/why it works, or you're considering a contribution / merge into apm |
| [usage.md](./docs/usage.md) | Day-to-day reference — every command, common recipes, troubleshooting |

## Install

Prereqs: `apm` ≥ 0.16, Python 3.9+, `click`, `pyyaml`.

```bash
# Python deps (user-scope)
python3 -m pip install --user click pyyaml

# Place the script and symlink onto PATH
ln -sfn "$HOME/src/imenkov/apm-overlay/tools/apm-overlay" \
        "$HOME/.local/bin/apm-overlay"

# Point at your overlay library (default: ~/.apm/overlays/)
echo 'export APM_OVERLAYS_DIR="$HOME/src/imenkov/apm-overlay/overlays"' \
    >> ~/.zshrc
```

Re-source your shell, then verify:

```bash
apm-overlay --version
apm-overlay list
```

## 30-second tour

```bash
# What's available?
apm-overlay list
apm-overlay show learn-ai

# Apply an overlay globally (or omit -g for the current project)
apm-overlay install learn-ai -g
apm-overlay status -g

# Undo — only removes what THIS overlay added
apm-overlay uninstall learn-ai -g
```

Every command supports `--dry-run` for previewing and `-v` to print the exact
`apm` invocation under the hood.

## Authoring an overlay

An overlay is a regular apm project. Scaffold one with apm itself:

```bash
cd "$APM_OVERLAYS_DIR"
apm plugin init my-overlay -y --target copilot
$EDITOR my-overlay/apm.yml          # add packages under dependencies.apm
```

Only `description` and `dependencies` are read by `apm-overlay`; the rest is
standard apm metadata and is preserved (so the overlay can also be tested with
plain `apm install`).

See [usage.md](./docs/usage.md) for the full reference and
[architecture.md](./docs/architecture.md) for design details.
