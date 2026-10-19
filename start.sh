#!/usr/bin/env bash
# Fuelora: set up on first run, fetch the latest prices, start the server, and open the page.
# Usage (Linux / macOS):  ./start.sh      (or: bash start.sh)
set -u
cd "$(dirname "$0")"

echo "Warning: this script has not been tested on macOS or Linux yet. Please report any problems."

PY=""
for candidate in python3 python; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/"
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "First run: setting up a private Python environment in .venv ..."
  "$PY" -m venv .venv || { echo "Could not create .venv."; exit 1; }
fi
VENV_PY=".venv/bin/python"

"$VENV_PY" -m pip install --quiet -r requirements.txt || { echo "Could not install requirements."; exit 1; }

echo "Fetching the latest prices ..."
if ! "$VENV_PY" app/server.py --fetch-only; then
  echo "Warning: the fetch failed. Showing the last saved prices instead."
fi

URL="http://127.0.0.1:8000"
(
  sleep 2
  if command -v open >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  else echo "Open $URL in your browser."
  fi
) &

exec "$VENV_PY" app/server.py
