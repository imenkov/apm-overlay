# Overlay library

Each subdirectory here is an **apm-overlay** — a regular apm project
(`apm.yml`, optionally with `plugin.json`) whose `dependencies.apm` section
declares the packages the overlay contributes.

For the full story see [`../docs/`](../docs/):

- [README.md](../README.md) — overview, install, quick start
- [usage.md](../docs/usage.md) — command reference & recipes
- [architecture.md](../docs/architecture.md) — design rationale

## Quick reference

```bash
export APM_OVERLAYS_DIR="$(pwd)"

apm-overlay list
apm-overlay install <name> [-g] [--target <target>]
apm-overlay uninstall <name> [-g] [--target <target>]
apm-overlay status [-g]
```

## Authoring

```bash
apm plugin init <overlay-name> -y --target copilot
$EDITOR <overlay-name>/apm.yml        # add packages under dependencies.apm
```
