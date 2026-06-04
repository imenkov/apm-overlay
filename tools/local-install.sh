#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN_DIR="${HOME}/.local/bin"
OVERLAYS_DIR="${REPO_DIR}/overlays"
PYTHON_BIN="python3"
SHELL_RC=""
DRY_RUN=0

usage() {
  cat <<'EOF'
Install apm-overlay locally.

Usage:
  ./tools/local-install.sh [options]

Options:
  --repo-dir PATH       Path to apm-overlay repo (default: script parent)
  --bin-dir PATH        Bin directory for launcher (default: ~/.local/bin)
  --overlays-dir PATH   APM_OVERLAYS_DIR value (default: <repo>/overlays)
  --python PATH         Python executable (default: python3)
  --shell-rc PATH       Shell rc file to update (default: auto-detect)
  --dry-run             Print actions without changing files
  -h, --help            Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo-dir)
      REPO_DIR="$2"
      shift 2
      ;;
    --bin-dir)
      BIN_DIR="$2"
      shift 2
      ;;
    --overlays-dir)
      OVERLAYS_DIR="$2"
      shift 2
      ;;
    --python)
      PYTHON_BIN="$2"
      shift 2
      ;;
    --shell-rc)
      SHELL_RC="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 2
      ;;
  esac
done

REPO_DIR="$(cd "$REPO_DIR" && pwd)"
SCRIPT_PATH="${REPO_DIR}/tools/apm-overlay"
VENV_DIR="${REPO_DIR}/.venv"
VENV_PY="${VENV_DIR}/bin/python"
LAUNCHER_PATH="${BIN_DIR}/apm-overlay"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "Expected script not found: $SCRIPT_PATH" >&2
  exit 1
fi

if ! command -v "$PYTHON_BIN" >/dev/null 2>&1; then
  echo "Python not found: $PYTHON_BIN" >&2
  exit 1
fi

if [[ -z "$SHELL_RC" ]]; then
  shell_name="$(basename "${SHELL:-}")"
  case "$shell_name" in
    zsh) SHELL_RC="${HOME}/.zshrc" ;;
    bash) SHELL_RC="${HOME}/.bashrc" ;;
    *) SHELL_RC="${HOME}/.profile" ;;
  esac
fi

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

append_if_missing() {
  local line="$1"
  local file="$2"
  if [[ -f "$file" ]] && grep -Fqx "$line" "$file"; then
    return 0
  fi
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] append to ${file}: ${line}"
    return 0
  fi
  touch "$file"
  printf '%s\n' "$line" >> "$file"
}

path_export_line() {
  case "$BIN_DIR" in
    "$HOME"/*)
      rel="${BIN_DIR#"$HOME"/}"
      printf 'export PATH="%s:$PATH"' "\$HOME/$rel"
      ;;
    *)
      printf 'export PATH="%s:$PATH"' "$BIN_DIR"
      ;;
  esac
}

echo "Installing apm-overlay from ${REPO_DIR}"
run mkdir -p "$BIN_DIR"

if [[ ! -d "$VENV_DIR" ]]; then
  run "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

run "$VENV_PY" -m pip install --upgrade pip
run "$VENV_PY" -m pip install click pyyaml

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[dry-run] write launcher ${LAUNCHER_PATH}"
else
  cat > "$LAUNCHER_PATH" <<EOF
#!/usr/bin/env bash
exec "${VENV_PY}" "${SCRIPT_PATH}" "\$@"
EOF
  chmod +x "$LAUNCHER_PATH"
fi

append_if_missing "$(path_export_line)" "$SHELL_RC"
append_if_missing "export APM_OVERLAYS_DIR=\"${OVERLAYS_DIR}\"" "$SHELL_RC"

echo
echo "Install complete."
echo "Reload your shell and verify:"
echo "  source ${SHELL_RC}"
echo "  apm-overlay --version"
echo "  apm-overlay list"
