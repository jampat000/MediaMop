#!/bin/sh
set -e

export WEIR_HOME="${WEIR_HOME:-/data/weir}"
WEIR_PUID="${WEIR_PUID:-${PUID:-1000}}"
WEIR_PGID="${WEIR_PGID:-${PGID:-1000}}"
WEIR_CHOWN_WATCHED="${WEIR_CHOWN_WATCHED:-false}"
WEIR_CHOWN_TEMP="${WEIR_CHOWN_TEMP:-false}"
WEIR_CHOWN_OUTPUT="${WEIR_CHOWN_OUTPUT:-false}"
WEIR_DIR_MODE_WATCHED="${WEIR_DIR_MODE_WATCHED:-}"
WEIR_DIR_MODE_TEMP="${WEIR_DIR_MODE_TEMP:-}"
WEIR_DIR_MODE_OUTPUT="${WEIR_DIR_MODE_OUTPUT:-}"

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
  if [ -n "${WEIR_DB_PATH:-}" ]; then
    case "$WEIR_DB_PATH" in
      /*) printf '%s\n' "$WEIR_DB_PATH" ;;
      *) printf '%s/%s\n' "$WEIR_HOME" "$WEIR_DB_PATH" ;;
    esac
    return
  fi
  printf '%s/data/weir.sqlite3\n' "$WEIR_HOME"
}

update_runtime_identity() {
  current_gid="$(getent group weir | cut -d: -f3)"
  current_uid="$(id -u weir)"
  if [ "$current_gid" != "$WEIR_PGID" ]; then
    log_info "Updating weir group id to $WEIR_PGID"
    groupmod -o -g "$WEIR_PGID" weir
  fi
  if [ "$current_uid" != "$WEIR_PUID" ]; then
    log_info "Updating weir user id to $WEIR_PUID"
    usermod -o -u "$WEIR_PUID" -g "$WEIR_PGID" weir
  fi
}

ensure_runtime_home_ownership() {
  mkdir -p "$WEIR_HOME"
  chown -R weir:weir "$WEIR_HOME" /opt/weir /home/weir
}

apply_refiner_permissions() {
  include_watched=0
  include_temp=0
  include_output=0
  if bool_enabled "$WEIR_CHOWN_WATCHED" || [ -n "$WEIR_DIR_MODE_WATCHED" ]; then
    include_watched=1
  fi
  if bool_enabled "$WEIR_CHOWN_TEMP" || [ -n "$WEIR_DIR_MODE_TEMP" ]; then
    include_temp=1
  fi
  if bool_enabled "$WEIR_CHOWN_OUTPUT" || [ -n "$WEIR_DIR_MODE_OUTPUT" ]; then
    include_output=1
  fi

  if [ "$include_watched" -eq 0 ] &&
     [ "$include_temp" -eq 0 ] &&
     [ "$include_output" -eq 0 ]; then
    return
  fi

  db_path="$(resolve_db_path)"
  set -- /opt/weir/.venv/bin/python -m weir.platform.docker_runtime apply-refiner-permissions \
    --db-path "$db_path" \
    --uid "$WEIR_PUID" \
    --gid "$WEIR_PGID"

  if [ "$include_watched" -eq 1 ]; then
    set -- "$@" --include-watched
  fi
  if [ "$include_temp" -eq 1 ]; then
    set -- "$@" --include-temp
  fi
  if [ "$include_output" -eq 1 ]; then
    set -- "$@" --include-output
  fi
  if [ -n "$WEIR_DIR_MODE_WATCHED" ]; then
    set -- "$@" --watched-dir-mode "$WEIR_DIR_MODE_WATCHED"
  fi
  if [ -n "$WEIR_DIR_MODE_TEMP" ]; then
    set -- "$@" --temp-dir-mode "$WEIR_DIR_MODE_TEMP"
  fi
  if [ -n "$WEIR_DIR_MODE_OUTPUT" ]; then
    set -- "$@" --output-dir-mode "$WEIR_DIR_MODE_OUTPUT"
  fi

  log_info "Applying optional Refiner path ownership policy"
  "$@"
}

run_app() {
  cd /opt/weir/apps/backend
  alembic upgrade head
  exec uvicorn weir.api.main:app --host 0.0.0.0 --port "${PORT:-8788}" --no-server-header
}

validate_uint "$WEIR_PUID" "WEIR_PUID"
validate_uint "$WEIR_PGID" "WEIR_PGID"
validate_boolish "$WEIR_CHOWN_WATCHED" "WEIR_CHOWN_WATCHED"
validate_boolish "$WEIR_CHOWN_TEMP" "WEIR_CHOWN_TEMP"
validate_boolish "$WEIR_CHOWN_OUTPUT" "WEIR_CHOWN_OUTPUT"
validate_dir_mode "$WEIR_DIR_MODE_WATCHED" "WEIR_DIR_MODE_WATCHED"
validate_dir_mode "$WEIR_DIR_MODE_TEMP" "WEIR_DIR_MODE_TEMP"
validate_dir_mode "$WEIR_DIR_MODE_OUTPUT" "WEIR_DIR_MODE_OUTPUT"
mkdir -p "$WEIR_HOME"

generate_secret() {
  python - <<'PY'
import secrets
print(secrets.token_urlsafe(48))
PY
}

if [ -z "${WEIR_SESSION_SECRET:-}" ]; then
  secret_file="$WEIR_HOME/session.secret"
  if [ -f "$secret_file" ]; then
    WEIR_SESSION_SECRET="$(cat "$secret_file")"
  else
    WEIR_SESSION_SECRET="$(generate_secret)"
    umask 077
    printf '%s\n' "$WEIR_SESSION_SECRET" > "$secret_file"
    log_info "generated WEIR_SESSION_SECRET at $secret_file"
  fi
  export WEIR_SESSION_SECRET
fi

# Fernet-backed features and session signing expect adequate entropy.
if [ "${#WEIR_SESSION_SECRET}" -lt 32 ]; then
  fail "WEIR_SESSION_SECRET must be at least 32 characters (try: openssl rand -hex 32)"
fi

if [ "$(id -u)" -eq 0 ]; then
  update_runtime_identity
  ensure_runtime_home_ownership
  if [ -f "$WEIR_HOME/session.secret" ]; then
    chown weir:weir "$WEIR_HOME/session.secret"
  fi
  gosu weir sh -c 'cd /opt/weir/apps/backend && alembic upgrade head'
  apply_refiner_permissions
  cd /opt/weir/apps/backend
  exec gosu weir uvicorn weir.api.main:app --host 0.0.0.0 --port "${PORT:-8788}" --no-server-header
fi

run_app
