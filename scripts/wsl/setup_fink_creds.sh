#!/usr/bin/env bash
# setup_fink_creds.sh — copy the user's fink_client YAML from Windows
# into WSL and validate it with `fink_client_register --info`.
#
# Usage:
#   bash scripts/wsl/setup_fink_creds.sh /mnt/c/Users/Main/fink_client.yml
#
# After success, the creds live at ~/.finkclient/credentials.yml and
# the Rubin Anomaly Hunter pipeline can find them via the default
# fink-client resolution path.

set -euo pipefail

SRC="${1:-}"
if [ -z "$SRC" ]; then
  echo "usage: $0 /mnt/c/Users/<you>/fink_client.yml" >&2
  exit 2
fi
if [ ! -f "$SRC" ]; then
  echo "error: file not found: $SRC" >&2
  exit 1
fi

DEST_DIR="$HOME/.finkclient"
mkdir -p "$DEST_DIR"
chmod 700 "$DEST_DIR"
cp "$SRC" "$DEST_DIR/credentials.yml"
chmod 600 "$DEST_DIR/credentials.yml"

echo "Credentials copied to $DEST_DIR/credentials.yml"

# Activate the venv if present and validate.
VENV="${RUBIN_HUNTER_VENV:-$HOME/rubin-hunter.venv}"
if [ -d "$VENV" ]; then
  # shellcheck source=/dev/null
  source "$VENV/bin/activate"
fi

if command -v fink_client_register >/dev/null 2>&1; then
  echo "Validating with fink-client…"
  fink_client_register --info || true
else
  echo "fink-client CLI not found; activate the venv and retry:"
  echo "  source \$RUBIN_HUNTER_VENV/bin/activate"
fi
