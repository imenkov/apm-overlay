#!/bin/sh
set -eu

# apm-overlay bootstrap installer (macOS/Linux)
# Usage:
#   curl -sSL https://raw.githubusercontent.com/imenkov/apm-overlay/main/install.sh | sh
#
# Options:
#   VERSION=v0.1.0  # branch or tag; defaults to main
#   APM_OVERLAY_REPO=owner/repo
#   APM_OVERLAY_HOME=$HOME/.local/share/apm-overlay
#   APM_OVERLAY_BIN_DIR=$HOME/.local/bin
#   APM_OVERLAYS_DIR=$HOME/.local/share/apm-overlay/overlays

BLUE='\033[0;34m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

APM_OVERLAY_REPO="${APM_OVERLAY_REPO:-imenkov/apm-overlay}"
APM_OVERLAY_HOME="${APM_OVERLAY_HOME:-$HOME/.local/share/apm-overlay}"
APM_OVERLAY_BIN_DIR="${APM_OVERLAY_BIN_DIR:-$HOME/.local/bin}"

VERSION_INPUT="${VERSION:-}"
if [ -z "$VERSION_INPUT" ] && [ "${1:-}" != "" ]; then
  VERSION_INPUT="${1#@}"
fi
VERSION_INPUT="${VERSION_INPUT:-main}"

if ! command -v git >/dev/null 2>&1; then
  echo "${RED}Error: git is required but not found on PATH.${NC}" >&2
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  echo "${RED}Error: python3 is required but not found on PATH.${NC}" >&2
  exit 1
fi

echo "${BLUE}Installing apm-overlay (${VERSION_INPUT})...${NC}"

if [ -d "$APM_OVERLAY_HOME/.git" ]; then
  echo "${BLUE}Updating existing checkout at $APM_OVERLAY_HOME${NC}"
  git -C "$APM_OVERLAY_HOME" fetch --tags --prune origin
else
  echo "${BLUE}Cloning $APM_OVERLAY_REPO into $APM_OVERLAY_HOME${NC}"
  mkdir -p "$(dirname "$APM_OVERLAY_HOME")"
  git clone "https://github.com/$APM_OVERLAY_REPO.git" "$APM_OVERLAY_HOME"
fi

if git -C "$APM_OVERLAY_HOME" rev-parse --verify "$VERSION_INPUT" >/dev/null 2>&1; then
  git -C "$APM_OVERLAY_HOME" checkout "$VERSION_INPUT"
else
  git -C "$APM_OVERLAY_HOME" checkout "origin/$VERSION_INPUT"
fi

APM_OVERLAYS_DIR="${APM_OVERLAYS_DIR:-$APM_OVERLAY_HOME/overlays}"

echo "${BLUE}Running local installer...${NC}"
bash "$APM_OVERLAY_HOME/tools/local-install.sh" \
  --repo-dir "$APM_OVERLAY_HOME" \
  --bin-dir "$APM_OVERLAY_BIN_DIR" \
  --overlays-dir "$APM_OVERLAYS_DIR"

echo ""
echo "${GREEN}Bootstrap install complete.${NC}"
echo "${YELLOW}If this is a new shell session, run:${NC}"
echo "  source ~/.zshrc"
echo "  apm-overlay --version"
