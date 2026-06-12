#!/usr/bin/env bash
#
# Interim off-site backup of the credentials file (PRD #130, stage 1).
#
# Litestream continuously replicates the SQLite DB to R2 but NOT users.txt —
# until credentials move into the app database (PRD #130 stage 4), the file is
# the one piece of irreplaceable state a volume loss would not recover. This
# loop copies it to the same R2 bucket Litestream replicates to, so losing the
# volume no longer means losing every login. rclone skips the transfer when the
# file is unchanged (size + modtime), so the steady-state cost is one HEAD per
# tick.
#
# Config via env (with defaults):
#   USERS_FILE                     credentials file        (/data/users.txt)
#   USERS_BACKUP_DEST              rclone destination      (derived from LITESTREAM_*)
#   USERS_BACKUP_INTERVAL_SECONDS  loop interval           (300)
#
# Without an explicit USERS_BACKUP_DEST, the destination is built from the
# LITESTREAM_* env: those are the machine's *write-capable* R2 credentials
# (the RCLONE_CONFIG_R2_* token is read-only — it only ever pulls the
# composite onto the volume). The remote is configured via RCLONE_CONFIG_*
# env, never argv, so the keys never show in a process list;
# --s3-no-check-bucket skips the HeadBucket/CreateBucket probe a
# bucket-scoped R2 token is not allowed to make.
#
# `--once` runs a single copy and exits (the test harness uses this with a
# local-path destination; rclone needs no remote config for local paths).
# Unconfigured (no destination derivable) or a missing source file exits 0
# quietly, so a local/dev run of the process tree never crash-loops.
set -euo pipefail

USERS_FILE="${USERS_FILE:-/data/users.txt}"
INTERVAL="${USERS_BACKUP_INTERVAL_SECONDS:-300}"
DEST="${USERS_BACKUP_DEST:-}"
if [[ -z "${DEST}" && -n "${LITESTREAM_BUCKET:-}" && -n "${LITESTREAM_ACCESS_KEY_ID:-}" ]]; then
  export RCLONE_CONFIG_USERSBK_TYPE=s3
  export RCLONE_CONFIG_USERSBK_PROVIDER=Cloudflare
  export RCLONE_CONFIG_USERSBK_ACCESS_KEY_ID="${LITESTREAM_ACCESS_KEY_ID}"
  export RCLONE_CONFIG_USERSBK_SECRET_ACCESS_KEY="${LITESTREAM_SECRET_ACCESS_KEY:-}"
  export RCLONE_CONFIG_USERSBK_ENDPOINT="${LITESTREAM_ENDPOINT:-}"
  export RCLONE_CONFIG_USERSBK_REGION="${LITESTREAM_REGION:-auto}"
  export RCLONE_CONFIG_USERSBK_FORCE_PATH_STYLE=true
  DEST="usersbk:${LITESTREAM_BUCKET}/users.txt"
fi

log() { printf 'backup_users: %s\n' "$*"; }

if [[ -z "${DEST}" ]]; then
  log "no destination (set USERS_BACKUP_DEST or LITESTREAM_BUCKET) — exiting"
  exit 0
fi

command -v rclone >/dev/null 2>&1 || {
  log "rclone not found — exiting"
  exit 0
}

copy_once() {
  if [[ ! -f "${USERS_FILE}" ]]; then
    log "source ${USERS_FILE} missing — skipping"
    return 0
  fi
  if rclone copyto --s3-no-check-bucket "${USERS_FILE}" "${DEST}"; then
    log "copied ${USERS_FILE} -> ${DEST}"
  else
    # Log and carry on — a transient R2 hiccup must not kill the loop; the
    # next tick retries.
    log "copy failed (will retry next tick)"
  fi
}

if [[ "${1:-}" == "--once" ]]; then
  copy_once
  exit 0
fi

log "watching ${USERS_FILE} -> ${DEST} every ${INTERVAL}s"
while true; do
  copy_once
  sleep "${INTERVAL}"
done
