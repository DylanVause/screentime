#!/usr/bin/env bash
# Development / quick-start launcher.
# For production use the systemd service instead (see setup.sh).
set -e

cd "$(dirname "$0")"

if [ ! -f ".venv/bin/activate" ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q -r requirements.txt
fi

source .venv/bin/activate

export SECRET_KEY="${SECRET_KEY:-$(python3 -c 'import secrets; print(secrets.token_hex(32))')}"
export DB_PATH="${DB_PATH:-screentime.db}"
export PORT="${PORT:-5000}"

echo "Starting ScreenTime server on http://0.0.0.0:$PORT"
exec gunicorn app:app \
  --bind "0.0.0.0:$PORT" \
  --workers 2 \
  --timeout 60 \
  --access-logfile - \
  --error-logfile -
