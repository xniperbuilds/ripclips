#!/usr/bin/env bash
# =====================================================================
# RipClips - one-command setup for macOS / Linux
#   Run:  bash setup.sh
# =====================================================================
set -e
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

have() { command -v "$1" >/dev/null 2>&1; }

echo "== RipClips setup =="

# --- Python ---
if have python3; then PY=python3; elif have python; then PY=python; else
  echo "Python 3.9+ not found. Install it and re-run." >&2; exit 1
fi
echo "[ok] python: $($PY --version 2>&1)"

# --- virtual environment ---
if [ ! -d "$ROOT/.venv" ]; then
  echo "Creating virtual environment (.venv) ..."
  "$PY" -m venv .venv
fi
VPY="$ROOT/.venv/bin/python"

# --- python deps ---
echo "Installing Python dependencies ..."
"$VPY" -m pip install --upgrade pip >/dev/null
"$VPY" -m pip install -r "$ROOT/requirements.txt"

# --- ffmpeg ---
if have ffmpeg; then
  echo "[ok] ffmpeg found on PATH"
else
  echo "ffmpeg not found - attempting install ..."
  if have brew; then brew install ffmpeg
  elif have apt-get; then sudo apt-get update && sudo apt-get install -y ffmpeg
  elif have dnf; then sudo dnf install -y ffmpeg
  elif have pacman; then sudo pacman -S --noconfirm ffmpeg
  else echo "Install ffmpeg manually: https://ffmpeg.org/download.html"; fi
fi

echo ""
echo "Setup complete."
echo "Activate the venv with:  source .venv/bin/activate"
echo "Then hand a YouTube URL to your AI agent (Claude Code / Codex) - it reads AGENTS.md and runs the pipeline."
