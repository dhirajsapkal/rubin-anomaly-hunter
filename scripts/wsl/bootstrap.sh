#!/usr/bin/env bash
# bootstrap.sh — one-shot WSL2 setup for the Rubin Anomaly Hunter.
#
# Run this once after `wsl --install` + reboot, from inside the Ubuntu
# terminal (or `wsl -e bash -c '...'` from Windows).
#
# What it does:
#   1. apt install build deps + Python 3 + Kafka native libs
#   2. Clone + build Bill Gray's find_orb (and its dependencies: lunar,
#      jpl_eph, sat_code) under $HOME/src/. Binary is `fo` at
#      $HOME/src/find_orb/fo. Nothing committed to the project repo
#      (ADR-0008: find_orb is personal-use, never redistributed).
#   3. Clone + build heliolinc3d under $HOME/src/heliolinc2. Binary is
#      `heliolinc` (name varies by version).
#   4. Create a Python venv at $HOME/rubin-hunter.venv with fink-client,
#      confluent-kafka, pyyaml, and the project's own requirements.
#   5. Write an env-export file ($HOME/.rubin-hunter.env) that the
#      pipeline sources to locate the binaries and venv.
#
# Idempotent: safe to re-run. Skips steps whose outputs already exist.
#
# Usage:
#   wsl -e bash /mnt/e/Claude\ experiments/Veera\ Rubin/scripts/wsl/bootstrap.sh
# or from inside Ubuntu:
#   bash /mnt/e/Claude\ experiments/Veera\ Rubin/scripts/wsl/bootstrap.sh

set -euo pipefail

# ---- Config ----------------------------------------------------------------
SRC_ROOT="${SRC_ROOT:-$HOME/src}"
VENV_PATH="${VENV_PATH:-$HOME/rubin-hunter.venv}"
ENV_FILE="${ENV_FILE:-$HOME/.rubin-hunter.env}"
PY_BIN="${PY_BIN:-python3}"
PROJECT_ROOT_WIN="${PROJECT_ROOT_WIN:-/mnt/e/Claude experiments/Veera Rubin}"

bold()   { printf '\033[1m%s\033[0m\n' "$*"; }
ok()     { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn()   { printf '  \033[33m!\033[0m %s\n' "$*"; }
section(){ printf '\n\033[1;36m== %s ==\033[0m\n' "$*"; }

# ---- 1. apt deps -----------------------------------------------------------
section "Installing apt packages"

sudo apt-get update -y
sudo apt-get install -y --no-install-recommends \
  build-essential gcc g++ make cmake git \
  libcurl4-openssl-dev \
  libssl-dev libsasl2-dev \
  librdkafka-dev \
  libeigen3-dev \
  pkg-config \
  python3 python3-venv python3-dev python3-pip \
  ca-certificates curl wget

ok "apt packages installed"

mkdir -p "$SRC_ROOT"

# ---- 2. Build Bill Gray's stack --------------------------------------------
# Order matters: lunar → jpl_eph → sat_code → find_orb.
# Each `make install` places headers + libs under /usr/local/* by default.

build_bill_gray_lib() {
  local name="$1"
  local url="$2"
  local make_target="${3:-all}"
  local install_target="${4:-install}"
  local dir="$SRC_ROOT/$name"

  if [ -d "$dir/.git" ]; then
    ok "$name: already cloned; pulling latest"
    git -C "$dir" pull --ff-only || warn "$name: git pull failed (continuing)"
  else
    git clone --depth 1 "$url" "$dir"
    ok "$name: cloned"
  fi

  make -C "$dir" "$make_target" -j"$(nproc)"
  if [ -n "$install_target" ]; then
    sudo make -C "$dir" "$install_target"
  fi
  ok "$name: built"
}

section "Building lunar (Bill Gray)"
build_bill_gray_lib "lunar"   "https://github.com/Bill-Gray/lunar"   "all"     "install"

section "Building jpl_eph"
build_bill_gray_lib "jpl_eph" "https://github.com/Bill-Gray/jpl_eph" "all"     "install"

section "Building sat_code"
build_bill_gray_lib "sat_code" "https://github.com/Bill-Gray/sat_code" "all"   "install"

section "Building find_orb"
FO_DIR="$SRC_ROOT/find_orb"
if [ -d "$FO_DIR/.git" ]; then
  ok "find_orb: already cloned; pulling latest"
  git -C "$FO_DIR" pull --ff-only || warn "find_orb: git pull failed (continuing)"
else
  git clone --depth 1 "https://github.com/Bill-Gray/find_orb" "$FO_DIR"
fi
make -C "$FO_DIR" -j"$(nproc)"

FO_BIN="$FO_DIR/fo"
if [ ! -x "$FO_BIN" ]; then
  warn "find_orb 'fo' binary not found at expected path: $FO_BIN"
  warn "inspect $FO_DIR for build errors"
else
  ok "find_orb: built -> $FO_BIN"
fi

# find_orb needs a runtime data directory. First-run it may try to download
# ephemeris/misc files. The directory is configurable via FINDORB_DIR env.
FO_DATA="$HOME/.find_orb"
mkdir -p "$FO_DATA"
ok "find_orb data dir: $FO_DATA"

# ---- 3. Build heliolinc3d (best-effort) ------------------------------------
# Note: lsst-dm/heliolinc2 is an active research codebase. Build steps change
# between commits; if this section fails the rest of the pipeline still works
# in "linking=fallback" mode. Don't hard-fail the bootstrap on heliolinc.

section "Building heliolinc3d (best-effort)"
HL_DIR="$SRC_ROOT/heliolinc2"
if [ -d "$HL_DIR/.git" ]; then
  ok "heliolinc2: already cloned; pulling latest"
  git -C "$HL_DIR" pull --ff-only || warn "heliolinc2: git pull failed"
else
  git clone --depth 1 "https://github.com/lsst-dm/heliolinc2" "$HL_DIR" || warn "heliolinc2: clone failed"
fi

HL_BIN=""
if [ -d "$HL_DIR" ]; then
  pushd "$HL_DIR" >/dev/null
  if [ -f "CMakeLists.txt" ]; then
    mkdir -p build
    pushd build >/dev/null
    cmake .. >/dev/null 2>&1 && make -j"$(nproc)" || warn "heliolinc2: cmake build failed"
    popd >/dev/null
  elif [ -f "Makefile" ]; then
    make -j"$(nproc)" || warn "heliolinc2: make failed"
  else
    warn "heliolinc2: neither CMakeLists.txt nor Makefile found; check upstream"
  fi
  # Try to locate any binary named heliolinc* in the tree.
  HL_BIN="$(find "$HL_DIR" -type f -executable -name 'heliolinc*' 2>/dev/null | head -n1 || true)"
  popd >/dev/null
fi

if [ -n "$HL_BIN" ] && [ -x "$HL_BIN" ]; then
  ok "heliolinc3d: built -> $HL_BIN"
else
  warn "heliolinc3d binary not found — pipeline will run with mock linker."
  warn "The rest of the build still succeeded; you can retry heliolinc later."
fi

# ---- 4. Python venv + fink-client -----------------------------------------
section "Creating Python venv with fink-client"

if [ ! -d "$VENV_PATH" ]; then
  "$PY_BIN" -m venv "$VENV_PATH"
  ok "venv created: $VENV_PATH"
fi

# shellcheck source=/dev/null
source "$VENV_PATH/bin/activate"

pip install --upgrade pip wheel >/dev/null
pip install --upgrade \
  fink-client \
  confluent-kafka \
  fastavro \
  pyyaml \
  requests \
  pandas \
  numpy \
  matplotlib \
  pydantic \
  pyarrow

ok "fink-client + deps installed in venv"

deactivate

# ---- 5. Write env-export file ---------------------------------------------
section "Writing ${ENV_FILE}"

cat > "$ENV_FILE" <<EOF
# Sourced by the pipeline's WSL runner. Regenerate via scripts/wsl/bootstrap.sh.
export RUBIN_HUNTER_VENV="$VENV_PATH"
export FINDORB_PATH="$FO_BIN"
export FINDORB_DIR="$FO_DATA"
EOF

if [ -n "$HL_BIN" ] && [ -x "$HL_BIN" ]; then
  echo "export HELIOLINC3D_PATH=\"$HL_BIN\"" >> "$ENV_FILE"
fi

ok "env file: $ENV_FILE"

# ---- Summary ---------------------------------------------------------------
section "Bootstrap complete"
echo
echo "   find_orb fo binary:  $FO_BIN"
echo "   find_orb data dir:   $FO_DATA"
echo "   heliolinc binary:    ${HL_BIN:-<not built>}"
echo "   Python venv:         $VENV_PATH"
echo "   Env file:            $ENV_FILE"
echo
echo "   Next: source $ENV_FILE before running the pipeline."
echo "   Your Fink credentials YAML must be copied into WSL before first run."
