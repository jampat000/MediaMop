#!/bin/sh
set -e
if [ -z "${MEDIAMOP_SESSION_SECRET:-}" ]; then
  echo "error: MEDIAMOP_SESSION_SECRET must be set (min 32 characters recommended)" >&2
  exit 1
fi
export MEDIAMOP_HOME="${MEDIAMOP_HOME:-/data/mediamop}"
mkdir -p "$MEDIAMOP_HOME"
cd /opt/mediamop/apps/backend
alembic upgrade head
exec uvicorn mediamop.api.main:app --host 0.0.0.0 --port "${PORT:-8788}"
