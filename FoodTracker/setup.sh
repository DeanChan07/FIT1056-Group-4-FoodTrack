#!/usr/bin/env bash
# FoodShare Tracker setup for macOS and Linux.
# Builds a fresh .venv with Python 3.11 or newer, installs Streamlit and makes demo data.
#   Run from this folder:  bash setup.sh
set -euo pipefail
cd "$(dirname "$0")"

PYTHON=""
for candidate in python3.13 python3.12 python3.11 python3.14 python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 && \
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)' 2>/dev/null; then
    PYTHON="$candidate"; break
  fi
done
if [ -z "$PYTHON" ]; then
  echo "Python 3.11 or newer was not found."
  echo "Install it from https://www.python.org/downloads/ then run this again."
  exit 1
fi

echo "Using $PYTHON ($("$PYTHON" --version))"
rm -rf .venv
"$PYTHON" -m venv .venv
./.venv/bin/python -m pip install --upgrade pip --quiet
./.venv/bin/python -m pip install -r requirements.txt --quiet
[ -f data/foodshare.sqlite3 ] || ./.venv/bin/python seed.py

cat <<'MSG'

Ready.
  Start the app:  ./.venv/bin/python run.py      (opens http://localhost:8501)
  Run the tests:  ./.venv/bin/python -m pytest
  Demo sign-ins:  staff / recipient / volunteer / manager / admin
  Demo password:  DemoPassword123!
MSG
