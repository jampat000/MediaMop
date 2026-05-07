#!/bin/sh
set -e

export MEDIAMOP_HOME="${MEDIAMOP_HOME:-/data/mediamop}"
MEDIAMOP_PUID="${MEDIAMOP_PUID:-${PUID:-1000}}"
MEDIAMOP_PGID="${MEDIAMOP_PGID:-${PGID:-1000}}"
MEDIAMOP_CHOWN_WATCHED="${MEDIAMOP_CHOWN_WATCHED:-false}"
MEDIAMOP_CHOWN_TEMP="${MEDIAMOP_CHOWN_TEMP:-false}"
MEDIAMOP_CHOWN_OUTPUT="${MEDIAMOP_CHOWN_OUTPUT:-false}"
MEDIAMOP_DIR_MODE_WATCHED="${MEDIAMOP_DIR_MODE_WATCHED:-}"
MEDIAMOP_DIR_MODE_TEMP="${MEDIAMOP_DIR_MODE_TEMP:-}"
MEDIAMOP_DIR_MODE_OUTPUT="${MEDIAMOP_DIR_MODE_OUTPUT:-}"

log_info() {
  echo "info: $*" >&2
}

fail() {
  echo "error: $*" >&2
  exit 1
}

validate_uint() {
  value="$1"
  name="$2"
  case "$value" in
    ""|*[!0-9]*)
      fail "$name must be a non-negative integer."
      ;;
  esac
}

validate_boolish() {
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  name="$2"
  case "$value" in
    ""|0|1|true|false|yes|no|on|off)
      ;;
    *)
      fail "$name must be one of: true/false, 1/0, yes/no, on/off."
      ;;
  esac
}

validate_dir_mode() {
  value="$1"
  name="$2"
  if [ -z "$value" ]; then
    return
  fi
  case "$value" in
    *[!0-7]*)
      fail "$name must be an octal directory mode such as 775 or 2775."
      ;;
  esac
  case "${#value}" in
    3|4)
      ;;
    *)
      fail "$name must be an octal directory mode such as 775 or 2775."
      ;;
  esac
}

bool_enabled() {
  value="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')"
  case "$value" in
    1|true|yes|on)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

resolve_db_path() {
  if [ -n "${MEDIAMOP_DB_PATH:-}" ]; then
    case "$MEDIAMOP_DB_PATH" in
      /*) printf '%s\n' "$MEDIAMOP_DB_PATH" ;;
      *) printf '%s/%s\n' "$MEDIAMOP_HOME" "$MEDIAMOP_DB_PATH" ;;
    esac
    return
  fi
  printf '%s/data/mediamop.sqlite3\n' "$MEDIAMOP_HOME"
}

update_runtime_identity() {
  current_gid="$(getent group mediamop | cut -d: -f3)"
  current_uid="$(id -u mediamop)"
  if [ "$current_gid" != "$MEDIAMOP_PGID" ]; then
    log_info "Updating mediamop group id to $MEDIAMOP_PGID"
    groupmod -o -g "$MEDIAMOP_PGID" mediamop
  fi
  if [ "$current_uid" != "$MEDIAMOP_PUID" ]; then
    log_info "Updating mediamop user id to $MEDIAMOP_PUID"
    usermod -o -u "$MEDIAMOP_PUID" -g "$MEDIAMOP_PGID" mediamop
  fi
}

ensure_runtime_home_ownership() {
  mkdir -p "$MEDIAMOP_HOME"
  chown -R mediamop:mediamop "$MEDIAMOP_HOME" /opt/mediamop /home/mediamop
}

apply_refiner_permissions() {
  include_watched=0
  include_temp=0
  include_output=0
  if bool_enabled "$MEDIAMOP_CHOWN_WATCHED" || [ -n "$MEDIAMOP_DIR_MODE_WATCHED" ]; then
    include_watched=1
  fi
  if bool_enabled "$MEDIAMOP_CHOWN_TEMP" || [ -n "$MEDIAMOP_DIR_MODE_TEMP" ]; then
    include_temp=1
  fi
  if bool_enabled "$MEDIAMOP_CHOWN_OUTPUT" || [ -n "$MEDIAMOP_DIR_MODE_OUTPUT" ]; then
    include_output=1
  fi

  if [ "$include_watched" -eq 0 ] &&
     [ "$include_temp" -eq 0 ] &&
     [ "$include_output" -eq 0 ]; then
    return
  fi

  db_path="$(resolve_db_path)"
  set -- /opt/mediamop/.venv/bin/python -m mediamop.platform.docker_runtime apply-refiner-permissions \
    --db-path "$db_path" \
    --uid "$MEDIAMOP_PUID" \
    --gid "$MEDIAMOP_PGID"

  if [ "$include_watched" -eq 1 ]; then
    set -- "$@" --include-watched
  fi
  if [ "$include_temp" -eq 1 ]; then
    set -- "$@" --include-temp
  fi
  if [ "$include_output" -eq 1 ]; then
    set -- "$@" --include-output
  fi
  if [ -n "$MEDIAMOP_DIR_MODE_WATCHED" ]; then
    set -- "$@" --watched-dir-mode "$MEDIAMOP_DIR_MODE_WATCHED"
  fi
  if [ -n "$MEDIAMOP_DIR_MODE_TEMP" ]; then
    set -- "$@" --temp-dir-mode "$MEDIAMOP_DIR_MODE_TEMP"
  fi
  if [ -n "$MEDIAMOP_DIR_MODE_OUTPUT" ]; then
    set -- "$@" --output-dir-mode "$MEDIAMOP_DIR_MODE_OUTPUT"
  fi

  log_info "Applying optional Refiner path ownership policy"
  "$@"
}

run_app() {
  cd /opt/mediamop/apps/backend
  alembic upgrade head
  exec uvicorn mediamop.api.main:app --host 0.0.0.0 --port "${PORT:-8788}"
}

validate_uint "$MEDIAMOP_PUID" "MEDIAMOP_PUID"
validate_uint "$MEDIAMOP_PGID" "MEDIAMOP_PGID"
validate_boolish "$MEDIAMOP_CHOWN_WATCHED" "MEDIAMOP_CHOWN_WATCHED"
validate_boolish "$MEDIAMOP_CHOWN_TEMP" "MEDIAMOP_CHOWN_TEMP"
validate_boolish "$MEDIAMOP_CHOWN_OUTPUT" "MEDIAMOP_CHOWN_OUTPUT"
validate_dir_mode "$MEDIAMOP_DIR_MODE_WATCHED" "MEDIAMOP_DIR_MODE_WATCHED"
validate_dir_mode "$MEDIAMOP_DIR_MODE_TEMP" "MEDIAMOP_DIR_MODE_TEMP"
validate_dir_mode "$MEDIAMOP_DIR_MODE_OUTPUT" "MEDIAMOP_DIR_MODE_OUTPUT"
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
    log_info "generated MEDIAMOP_SESSION_SECRET at $secret_file"
  fi
  export MEDIAMOP_SESSION_SECRET
fi

# Fernet-backed features and session signing expect adequate entropy.
if [ "${#MEDIAMOP_SESSION_SECRET}" -lt 32 ]; then
  fail "MEDIAMOP_SESSION_SECRET must be at least 32 characters (try: openssl rand -hex 32)"
fi

if [ "$(id -u)" -eq 0 ]; then
  update_runtime_identity
  ensure_runtime_home_ownership
  if [ -f "$MEDIAMOP_HOME/session.secret" ]; then
    chown mediamop:mediamop "$MEDIAMOP_HOME/session.secret"
  fi
  gosu mediamop sh -c 'cd /opt/mediamop/apps/backend && alembic upgrade head'
  apply_refiner_permissions
  cd /opt/mediamop/apps/backend
  exec gosu mediamop uvicorn mediamop.api.main:app --host 0.0.0.0 --port "${PORT:-8788}"
fi

run_app
