# Usage

Complete command reference and common recipes for `apm-overlay`.

## Conventions

- All commands accept `-g/--global` to operate on user scope (`~/.apm/`).
  Without it, they operate on the **current working directory** (project
  scope).
- All mutating commands accept:
  - `--dry-run` — print the resolved `apm` command without executing.
  - `-v/--verbose` — echo the resolved `apm` command before executing.
- Overlay names are directory names under `$APM_OVERLAYS_DIR` (default
  `~/.apm/overlays/`).

## Command reference

### `apm-overlay list`

Show available overlays. No flags.

```bash
$ apm-overlay list
Overlays in /Users/me/src/imenkov/apm-overlay/overlays:
  learn-ai — AI Academy plugin from agency-microsoft/playground
```

### `apm-overlay show <name>`

Print the overlay's `apm.yml` (useful when authoring or auditing).

```bash
$ apm-overlay show learn-ai
name: learn-ai
...
dependencies:
  apm:
    - agency-microsoft/playground/plugins/ai-academy
  mcp: []
```

### `apm-overlay status [-g]`

Show which overlays are currently applied at the chosen scope, along with the
exact packages each overlay added.

```bash
$ apm-overlay status -g
Active overlays at global (~/.apm/):
  learn-ai  (applied 2026-06-02T12:39:48+00:00)
    + apm: agency-microsoft/playground/plugins/ai-academy
```

If nothing is active you get `(no overlays active at ...)`.

### `apm-overlay install <name> [-g] [--target <target>] [--dry-run] [-v]`

Apply an overlay. Behavior:

1. Reads `<APM_OVERLAYS_DIR>/<name>/apm.yml`.
2. Refuses if `<name>` is already active at the chosen scope.
3. Computes `to_install = overlay.deps − active.deps` (set difference).
4. Runs `apm install [-g] [--target <target>] <to_install...>` (single invocation; one lockfile
   update).
5. On success, records the additions in the state file.

```bash
# preview
apm-overlay install learn-ai -g --target copilot --dry-run
# real run, with the underlying command echoed
apm-overlay install learn-ai -g --target copilot -v
```

If every overlay package is already in the baseline, no `apm install` is run,
but an empty state entry is recorded so `uninstall` is a clean no-op.

### `apm-overlay uninstall <name> [-g] [--target <target>] [--dry-run] [-v]`

Remove an overlay. Behavior:

1. Refuses if the overlay is not active at the chosen scope.
2. Computes `to_remove = state[name].added − ⋃(other_active.added)` — any
   package still claimed by another active overlay is kept.
3. Runs `apm uninstall [-g] [--target <target>] <to_remove...>`.
4. On success, drops the state entry.

```bash
# preview
apm-overlay uninstall learn-ai -g --target copilot --dry-run
# real run
apm-overlay uninstall learn-ai -g --target copilot -v
```

When packages are skipped because another overlay still claims them, the tool
prints them so you know nothing was missed.

## Common recipes

### Apply once, work, undo

```bash
apm-overlay install adr-tools -g
# ... do the task ...
apm-overlay uninstall adr-tools -g
```

### Stack multiple overlays

```bash
apm-overlay install adr-tools -g
apm-overlay install security-review -g
apm-overlay status -g                   # both listed

apm-overlay uninstall security-review -g  # only its packages removed
apm-overlay status -g                   # adr-tools still active
```

If two overlays share a package, it stays until *all* claiming overlays are
uninstalled.

### Project-scope overlay (not global)

```bash
cd path/to/my-project           # must have an apm.yml
apm-overlay install code-review
# project apm.yml now includes the overlay's packages
apm-overlay status              # shows project-scope state
apm-overlay uninstall code-review
```

Project-scope state lives at `<project>/apm.overlays.json` — add it to your
project's `.gitignore` if you don't want to commit it.

### Author a new overlay

```bash
cd "$APM_OVERLAYS_DIR"
apm plugin init my-task -y --target copilot
cd my-task
$EDITOR apm.yml         # add packages under dependencies.apm
# optionally test the overlay as a standalone apm project:
apm install --dry-run
# then publish via your overlay library repo (git push, etc.)
```

### Audit what a global apm install actually contains

```bash
apm-overlay status -g           # overlay contributions only
cat ~/.apm/apm.yml              # full baseline + overlay state from apm's POV
```

### Re-apply an overlay after editing

```bash
apm-overlay uninstall my-task -g
$EDITOR "$APM_OVERLAYS_DIR/my-task/apm.yml"
apm-overlay install my-task -g
```

(There is no `--force` re-apply in v1 by design — see
[architecture.md](./architecture.md#why-these-decisions).)

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `APM_OVERLAYS_DIR` | Where to find overlay subdirectories | `~/.apm/overlays/` |

Set it in your shell rc, e.g.:

```bash
export APM_OVERLAYS_DIR="$HOME/src/imenkov/apm-overlay/overlays"
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including successful `--dry-run`) |
| 1 | Click usage error (bad flag, missing argument, etc.) |
| 1 | `ClickException` raised by the tool (missing overlay, already active, etc.) — message printed to stderr |
| ≠0 | apm itself failed; state file is left untouched |

## Troubleshooting

### "Overlays directory does not exist"

`APM_OVERLAYS_DIR` is unset and `~/.apm/overlays/` does not exist. Either set
the env var or `mkdir -p ~/.apm/overlays`.

### "Overlay '<x>' not found"

The directory `<APM_OVERLAYS_DIR>/<x>/` either does not exist or has no
`apm.yml`. Run `apm-overlay list` to see what's available.

### "Overlay '<x>' is already active"

You tried to install an overlay that's already recorded as active at the
chosen scope. Either `apm-overlay status` to confirm, or `apm-overlay
uninstall <x>` first.

### "Overlay '<x>' is not active"

You tried to uninstall an overlay that's not in the state file. Probably the
wrong scope flag (`-g`) or the state file was cleared. `apm-overlay status`
to see what's actually tracked.

### apm fails mid-install

The tool will print the error and refuse to update the state file. Once you
fix the underlying problem (network, auth, conflicting version, etc.),
re-run `apm-overlay install <name>` — it is safe to retry.

### State file corrupted

```
Corrupt state file /Users/.../overlays.state.json: ...
```

Delete the file. You lose overlay tracking (so future `uninstall` won't know
what to remove), but apm's own state — `apm.yml`, lockfile, modules,
deployed primitives — is untouched. You can manually inspect `apm.yml` and
`apm uninstall` what shouldn't be there.

### Some primitives not deployed at global scope

That's an apm limitation, not this tool's. apm prints:

```
Some primitives are not supported: copilot (instructions); cursor (instructions); ...
```

If you need those primitives, install the affected packages at project scope
instead.

### MCP packages in an overlay

```
[!] MCP overlay dependencies are not yet supported by apm-overlay; ignoring: ...
```

v1 does not install MCP entries. Install them manually with `apm install
--mcp ...` if needed.
