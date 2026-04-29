#!/bin/sh
set -e

export MEDIAMOP_HOME="${MEDIAMOP_HOME:-/data/mediamop}"
mkdir -p "$MEDIAMOP_HOME"

generate_secret() {
  python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

if [ -z "${MEDIAMOP_SESSION_SECRET:-}" ]; then
  secret_file="$MEDIAMOP_HOME/session.secret"
  if [ -f "$secret_file" ]; then
    MEDIAMOP_SESSION_SECRET="$(cat "$secret_file")"
  else
    MEDIAMOP_SESSION_SECRET="$(generate_secret)"
    umask 077
    printf '%s\n' "$MEDIAMOP_SESSION_SECRET" > "$secret_file"
    echo "info: generated MEDIAMOP_SESSION_SECRET at $secret_file" >&2
  fi
  export MEDIAMOP_SESSION_SECRET
fi

# Fernet-backed features and session signing expect adequate entropy.
if [ "${#MEDIAMOP_SESSION_SECRET}" -lt 32 ]; then
  echo "error: MEDIAMOP_SESSION_SECRET must be at least 32 characters (try: openssl rand -hex 32)" >&2
  exit 1
fi

cd /opt/mediamop/apps/backend
alembic upgrade head
exec uvicorn mediamop.api.main:app --host 0.0.0.0 --port "${PORT:-8788}"
