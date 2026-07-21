#!/usr/bin/env bash
# Run the Rubberr relay server. Works on Y6 (Windows, via Git Bash / WSL) and Mac.
#
# Usage:
#   ./run.sh              # start the relay on 0.0.0.0:8765
#   RELAY_PORT=9000 ./run.sh
#
# On first run this creates a venv next to this script and installs
# requirements.txt into it. Subsequent runs reuse the venv.
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"

VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
  echo "relay: creating venv at $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

# Windows venvs put the interpreter in Scripts/, POSIX venvs in bin/.
if [ -f "$VENV_DIR/Scripts/python.exe" ]; then
  PY="$VENV_DIR/Scripts/python.exe"
else
  PY="$VENV_DIR/bin/python"
fi

"$PY" -m pip install -q --upgrade pip
"$PY" -m pip install -q -r requirements.txt

if [ ! -f "register_tokens.json" ]; then
  echo "relay: WARNING no register_tokens.json found — no companion will be able to register."
  echo "relay: copy register_tokens.example.json to register_tokens.json and fill in real tokens."
fi

exec "$PY" server.py
