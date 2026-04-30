#!/bin/sh
set -eu

DATA_DIR="${DATA_DIR:-/data}"
LOGO_DIR="${LOGO_DIR:-$DATA_DIR/logos}"

mkdir -p "$DATA_DIR" "$LOGO_DIR"

export DATABASE_URL="${DATABASE_URL:-sqlite+pysqlite:///$DATA_DIR/bricoprohq.db}"
export API_URL="${API_URL:-http://127.0.0.1:8000}"

if [ -d /app/frontend/public/logos ] && [ -z "$(ls -A "$LOGO_DIR" 2>/dev/null)" ]; then
  cp -R /app/frontend/public/logos/. "$LOGO_DIR"/
fi
rm -rf /app/frontend/public/logos
ln -s "$LOGO_DIR" /app/frontend/public/logos

uvicorn app.main:app --app-dir /app/backend --host 127.0.0.1 --port 8000 &
API_PID="$!"

cleanup() {
  kill "$API_PID" 2>/dev/null || true
  if [ -n "${WEB_PID:-}" ]; then
    kill "$WEB_PID" 2>/dev/null || true
  fi
}
trap cleanup INT TERM

python - <<'PY'
import sys
import time
import urllib.request

for _ in range(60):
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=2) as response:
            if response.status == 200:
                sys.exit(0)
    except Exception:
        time.sleep(1)

sys.exit("API did not become healthy in time")
PY

cd /app/frontend
npm start -- -H 0.0.0.0 -p 3000 &
WEB_PID="$!"

wait "$WEB_PID"
