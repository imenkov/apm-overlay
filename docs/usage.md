# Usage

Complete command reference and common recipes for `apm-overlay`.

## Conventions

- All commands accept `-g/--global` to operate on user scope (`~/.apm/`).
  Without it, they operate on the **current working directory** (project
  scope).
- All mutating commands accept:
  - `--dry-run` — print the resolved `apm` command without executing.
  - `-v/--verbose` — echo the resolved `apm` command before executing.
- Overlay names are directory names in the configured overlay libraries.
  `$APM_OVERLAYS_DIRS` accepts an `os.pathsep`-separated list (`:` on
  macOS/Linux, `;` on Windows). If it has no non-empty entries, the legacy
  `$APM_OVERLAYS_DIR` is used, then `~/.apm/overlays/`.

## Command reference

### `apm-overlay list`

Show available overlays. No flags.

```bash
$ apm-overlay list
Available overlays:
  automation — Automation plugins [source: /Users/me/team-overlays]
  docs-design — Documentation plugins [source: /Users/me/personal-overlays]
```

Every occurrence includes its source library. If the same name exists in more
than one library, each occurrence is marked `[AMBIGUOUS: N matches]`.

### `apm-overlay show <name>`

Print the overlay's `apm.yml` (useful when authoring or auditing).
The name must resolve uniquely across all configured libraries. Duplicate
names fail with an error that lists every matching path.

```bash
$ apm-overlay show automation
name: automation
...
dependencies:
  apm:
    - github/awesome-copilot/plugins/automate-this
    - ChromeDevTools/chrome-devtools-mcp
    - github/awesome-copilot/plugins/testing-automation
  mcp: []
```

### `apm-overlay status [-g]`

Show which overlays are currently applied, along with the exact packages each
overlay added.

- With no flag, lists **both** project and global scopes (global overlays are
  always active in every project).
- With `-g`, restricts output to the global scope only.

```bash
$ apm-overlay status -g
Active overlays at global (~/.apm/):
  automation  (applied 2026-06-02T12:39:48+00:00)
    + apm: github/awesome-copilot/plugins/automate-this
    + apm: ChromeDevTools/chrome-devtools-mcp
    + apm: github/awesome-copilot/plugins/testing-automation
```

If nothing is active at a given scope you get `(no overlays active at ...)`.

### `apm-overlay install <name> [-g] [--target <target>] [--dry-run] [-v]`

Apply an overlay. Behavior:

1. Searches every configured library for `<name>/apm.yml` and requires exactly
   one match.
2. Refuses if `<name>` is already active at the chosen scope.
3. Computes `to_install = overlay.deps − active.deps` (set difference).
4. Runs `apm install [-g] [--target <target>] <to_install...>` (single invocation; one lockfile
   update).
5. On success, records the additions in the state file.

New state entries also record the resolved overlay source path. Existing state
files without that field remain valid.

```bash
# preview
apm-overlay install automation -g --target copilot --dry-run
# real run, with the underlying command echoed
apm-overlay install automation -g --target copilot -v
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
apm-overlay uninstall automation -g --target copilot --dry-run
# real run
apm-overlay uninstall automation -g --target copilot -v
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
apm-overlay status              # shows project-scope state + global overlays
apm-overlay uninstall code-review
```

Project-scope state lives at `<project>/apm.overlays.json` — add it to your
project's `.gitignore` if you don't want to commit it.

### Author a new overlay

```bash
OVERLAY_LIBRARY="$HOME/src/my-overlays"
cd "$OVERLAY_LIBRARY"
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
$EDITOR "$HOME/src/my-overlays/my-task/apm.yml"
apm-overlay install my-task -g
```

(There is no `--force` re-apply in v1 by design — see
[architecture.md](./architecture.md#why-these-decisions).)

## Environment

| Variable | Purpose | Default |
|---|---|---|
| `APM_OVERLAYS_DIRS` | Path-separated overlay library list; non-empty entries win over the singular variable | unset |
| `APM_OVERLAYS_DIR` | Legacy single overlay library | unset |
| default | Used when neither variable configures a library | `~/.apm/overlays/` |

Set it in your shell rc, e.g.:

```bash
export APM_OVERLAYS_DIRS="$HOME/src/team-overlays:$HOME/src/personal-overlays"
```

Empty entries are ignored, `~` is expanded, and duplicate paths are removed
without changing the configured search order. Library order does not resolve
duplicate overlay names: `show` and `install` reject ambiguity rather than
silently choosing one.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success (including successful `--dry-run`) |
| 1 | Click usage error (bad flag, missing argument, etc.) |
| 1 | `ClickException` raised by the tool (missing overlay, already active, etc.) — message printed to stderr |
| ≠0 | apm itself failed; state file is left untouched |

## Troubleshooting

### "Overlays directory does not exist"

None of the configured libraries exists. Set `APM_OVERLAYS_DIRS` (or the
legacy `APM_OVERLAYS_DIR`) to an existing directory, or create
`~/.apm/overlays`.

### "Overlay '<x>' not found"

No configured library contains `<x>/apm.yml`. Run `apm-overlay list` to see
what is available and where each overlay came from.

### "Overlay '<x>' is ambiguous"

More than one configured library contains `<x>/apm.yml`. The error lists all
matches. Rename/remove a duplicate or adjust `APM_OVERLAYS_DIRS`; library
ordering is intentionally not used as silent precedence.

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
