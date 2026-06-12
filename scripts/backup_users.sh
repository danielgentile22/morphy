#!/usr/bin/env bash
#
# Interim off-site backup of the credentials file (PRD #130, stage 1).
#
# Litestream continuously replicates the SQLite DB to R2 but NOT users.txt —
# until credentials move into the app database (PRD #130 stage 4), the file is
# the one piece of irreplaceable state a volume loss would not recover. This
# loop copies it to the same R2 bucket Litestream replicates to, via the
# in-machine rclone (the RCLONE_CONFIG_R2_* Fly secrets), so losing the volume
# no longer means losing every login. rclone skips the transfer when the file
# is unchanged (size + modtime), so the steady-state cost is one HEAD per tick.
#
# Config via env (with defaults):
#   USERS_FILE                     credentials file        (/data/users.txt)
#   USERS_BACKUP_DEST              rclone destination      (r2:${LITESTREAM_BUCKET}/users.txt)
#   USERS_BACKUP_INTERVAL_SECONDS  loop interval           (300)
#
# `--once` runs a single copy and exits (the test harness uses this with a
# local-path destination; rclone needs no remote config for local paths).
# Unconfigured (no destination derivable) or a missing source file exits 0
# quietly, so a local/dev run of the process tree never crash-loops.
set -euo pipefail

USERS_FILE="${USERS_FILE:-/data/users.txt}"
INTERVAL="${USERS_BACKUP_INTERVAL_SECONDS:-300}"
DEST="${USERS_BACKUP_DEST:-}"
if [[ -z "${DEST}" && -n "${LITESTREAM_BUCKET:-}" ]]; then
  DEST="r2:${LITESTREAM_BUCKET}/users.txt"
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
  if rclone copyto "${USERS_FILE}" "${DEST}"; then
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
