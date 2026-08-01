#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"
if [ -z "${PYTHON_BIN:-}" ] && [ -x "$SCRIPT_DIR/.venv/bin/python" ]; then
    PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
else
    PYTHON_BIN="${PYTHON_BIN:-python3}"
fi
command -v "$PYTHON_BIN" >/dev/null 2>&1 || { echo "Python 3 not found."; exit 1; }
"$PYTHON_BIN" -m nova
