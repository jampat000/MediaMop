#!/bin/sh
set -e

# Entrypoint for the Weir image (Dockerfile). Validates the runtime settings, remaps the weir
# user to WEIR_PUID/WEIR_PGID, makes sure a session secret exists, then runs the .NET server as
# the unprivileged weir user. There is no separate migration step: the server creates or migrates
# its own SQLite database on start (apps/server/src/Weir.Host/WeirServer.cs, OpenDatabase).

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

warn_unported_processing_permissions() {
  # As of #555, Weir.Host applies WEIR_CHOWN_OUTPUT/WEIR_FILE_MODE_OUTPUT/WEIR_DIR_MODE_OUTPUT
  # itself, directly, right after it writes or creates each output file or folder (see
  # apps/server/README.md, "Output ownership (#555)") — this script's job for those three is
  # already done at that point, not here. WEIR_CHOWN_WATCHED/WEIR_CHOWN_TEMP/
  # WEIR_DIR_MODE_WATCHED/WEIR_DIR_MODE_TEMP still have no .NET equivalent, so the warning below
  # is still correct for those four; its wording covering all six together is now stale for the
  # output three specifically. Left as-is (a functional fix, not a doc fix); see docker/README.md.
  if bool_enabled "$WEIR_CHOWN_WATCHED" || [ -n "$WEIR_DIR_MODE_WATCHED" ] ||
     bool_enabled "$WEIR_CHOWN_TEMP" || [ -n "$WEIR_DIR_MODE_TEMP" ] ||
     bool_enabled "$WEIR_CHOWN_OUTPUT" || [ -n "$WEIR_DIR_MODE_OUTPUT" ]; then
    # The old policy read folders from processing_path_settings, a table removed when folders moved
    # onto libraries (#363), so it had already stopped changing anything. See docker/README.md.
    log_info "WEIR_CHOWN_*/WEIR_DIR_MODE_* are set, but this image does not apply the Processing" \
      "folder ownership policy (see docker/README.md). Ignoring them."
  fi
}

run_app() {
  cd /opt/weir
  exec ./Weir --port "${PORT:-8788}"
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
warn_unported_processing_permissions

generate_secret() {
  # No Python interpreter in this image. 48 random bytes, base64url-encoded without padding —
  # the same entropy as docker/entrypoint.sh's secrets.token_urlsafe(48), produced with coreutils
  # (already present in the runtime-deps base) instead.
  head -c 48 /dev/urandom | base64 | tr '+/' '-_' | tr -d '=\n'
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
  cd /opt/weir
  exec gosu weir ./Weir --port "${PORT:-8788}"
fi

run_app
