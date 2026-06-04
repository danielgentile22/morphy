#!/usr/bin/env bash
#
# Deploy the Phase-1 app to Fly + sync the served composite (PRD #96, ADR-064).
#
# Subcommands:
#   code    fly deploy — ship the image (SPA + FastAPI + Caddy + Litestream)
#   data    sync the served composite: laptop -> R2 -> volume. Excludes the
#           per-county parcels/ compose-inputs (~8.43 GB the app never fetches)
#           and mirrors (files dropped by a recompose are removed). Uses the
#           tested contract in scripts/sync_composite.py.
#   all     code, then data
#   smoke   post-deploy checks: SPA loads, /data serves 206 on Range, /api lives
#
# Safety: `data` is DRY-RUN by default (reports, writes nothing). Pass --apply
# (or DRY_RUN=0) to actually transfer. The R2->volume leg runs inside the
# machine via `fly ssh` (the image carries rclone + sync_composite.py).
#
# Config via env (with defaults):
#   FLY_APP        Fly app name              (pilot-app)
#   COMPOSITE_SRC  laptop composite dir      (data/processed/composite)
#   R2_REMOTE      rclone R2 path            (r2:pilot-composite/composite)
#   VOLUME_DEST    composite path on volume  (/data/processed/composite)
#   APP_URL        base URL for smoke        (https://$FLY_APP.fly.dev)
#   PYTHON         local python              (python3)
set -euo pipefail

FLY_APP="${FLY_APP:-pilot-app}"
COMPOSITE_SRC="${COMPOSITE_SRC:-data/processed/composite}"
R2_REMOTE="${R2_REMOTE:-r2:pilot-composite/composite}"
VOLUME_DEST="${VOLUME_DEST:-/data/processed/composite}"
APP_URL="${APP_URL:-https://${FLY_APP}.fly.dev}"
PYTHON="${PYTHON:-python3}"
DRY_RUN="${DRY_RUN:-1}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SYNC="${REPO_ROOT}/scripts/sync_composite.py"

log() { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
die() {
  printf '\033[1;31merror:\033[0m %s\n' "$*" >&2
  exit 1
}

need_fly() {
  command -v fly >/dev/null 2>&1 || die "flyctl not found — install it and 'fly auth login'"
}

deploy_code() {
  need_fly
  log "fly deploy --app ${FLY_APP}"
  fly deploy --app "${FLY_APP}"
}

# Run one leg through the tested contract. Explicit branches (rather than an
# optional-flag array) stay lint-clean and safe on macOS's bash 3.2, which
# errors on an empty array expanded under `set -u`.
run_sync_local() {  # $1=src $2=dst
  if [[ "${DRY_RUN}" == "1" ]]; then
    "${PYTHON}" "${SYNC}" "$1" "$2" --dry-run
  else
    "${PYTHON}" "${SYNC}" "$1" "$2"
  fi
}

sync_data() {
  need_fly
  if [[ "${DRY_RUN}" == "1" ]]; then
    log "DRY-RUN (pass --apply or DRY_RUN=0 to write)"
  fi

  # Leg 1: laptop -> R2 (local rclone; operator's 'r2' remote).
  log "leg 1/2: ${COMPOSITE_SRC} -> ${R2_REMOTE}"
  run_sync_local "${COMPOSITE_SRC}" "${R2_REMOTE}"

  # Leg 2: R2 -> volume, run inside the machine (image has rclone + the script).
  log "leg 2/2: ${R2_REMOTE} -> ${VOLUME_DEST} (on ${FLY_APP})"
  local remote_cmd="python3 /srv/scripts/sync_composite.py ${R2_REMOTE} ${VOLUME_DEST}"
  if [[ "${DRY_RUN}" == "1" ]]; then
    remote_cmd="${remote_cmd} --dry-run"
  fi
  fly ssh console --app "${FLY_APP}" -C "${remote_cmd}"
}

smoke() {
  log "smoke: ${APP_URL}"
  local code

  code="$(curl -fsS -o /dev/null -w '%{http_code}' "${APP_URL}/")" || die "SPA request failed"
  log "SPA          -> ${code}"

  code="$(curl -fsS -r 0-3 -o /dev/null -w '%{http_code}' \
    "${APP_URL}/data/processed/composite/index.json")" || die "data Range request failed"
  [[ "${code}" == "206" ]] || die "expected 206 on Range request, got ${code}"
  log "data Range   -> 206"

  code="$(curl -fsS -o /dev/null -w '%{http_code}' "${APP_URL}/api/health")" \
    || die "api/health request failed"
  [[ "${code}" == "200" ]] || die "api/health not 200 (got ${code})"
  log "api/health   -> 200"

  log "smoke OK (run /verify for the full login round-trip)"
}

main() {
  local cmd="${1:-}"
  shift || true
  # --apply anywhere on the line flips off dry-run.
  for arg in "$@"; do
    [[ "${arg}" == "--apply" ]] && DRY_RUN=0
  done

  [[ -f "${SYNC}" ]] || die "missing ${SYNC}"

  case "${cmd}" in
    code) deploy_code ;;
    data) sync_data ;;
    all)
      deploy_code
      sync_data
      ;;
    smoke) smoke ;;
    *)
      die "usage: $(basename "$0") {code|data|all|smoke} [--apply]"
      ;;
  esac
}

main "$@"
