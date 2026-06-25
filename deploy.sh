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
#   smoke   post-deploy checks: SPA loads, unauthenticated /data is REFUSED
#           (401/403 — the PRD #130 gate; this exposure must never regress),
#           /api lives
#
# Safety: `data` is DRY-RUN by default (reports, writes nothing). Pass --apply
# (or DRY_RUN=0) to actually transfer. The R2->volume leg runs inside the
# machine via `fly ssh` (the image carries rclone + sync_composite.py).
# `code` refuses to deploy a dirty working tree (fly builds the tree, not HEAD);
# set ALLOW_DIRTY=1 to override for a local experiment.
#
# Config via env (defaults are the live production values — a bare
# `./deploy.sh code` ships to prod; override FLY_APP/R2_REMOTE only for a
# different environment):
#   FLY_APP        Fly app name              (morphy-consulting)
#   COMPOSITE_SRC  laptop composite dir      (data/processed/composite)
#   R2_REMOTE      rclone R2 path            (r2:morphy-prod/composite)
#   VOLUME_DEST    composite path on volume  (/data/processed/composite)
#   APP_URL        base URL for smoke        (https://$FLY_APP.fly.dev)
#   PYTHON         local python              (python3)
#   VITE_MAPTILER_KEY  OPTIONAL override of the Satellite basemap key (the
#                  prod key is the Dockerfile ARG default; set this only to
#                  build with a different key)
set -euo pipefail

FLY_APP="${FLY_APP:-morphy-consulting}"
COMPOSITE_SRC="${COMPOSITE_SRC:-data/processed/composite}"
R2_REMOTE="${R2_REMOTE:-r2:morphy-prod/composite}"
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

# `fly deploy` ships the working tree (minus .dockerignore), NOT git HEAD — a
# dirty tree silently bakes in uncommitted edits, and a stale checkout omits
# merged work. Refuse unless the tree matches HEAD (ALLOW_DIRTY=1 to override).
# --porcelain ignores gitignored paths (data/, .venv/), so this only trips on
# changes that would actually reach the image.
require_clean_tree() {
  command -v git >/dev/null 2>&1 || die "git not found"
  if [[ "${ALLOW_DIRTY:-0}" == "1" ]]; then
    log "ALLOW_DIRTY=1 — skipping clean-tree check"
    return
  fi
  if [[ -n "$(git -C "${REPO_ROOT}" status --porcelain)" ]]; then
    git -C "${REPO_ROOT}" status --short >&2
    die "working tree is dirty — commit/stash first, or set ALLOW_DIRTY=1 to override"
  fi
}

# Snapshot the live puller manifest into the audit artifacts as freshness.json
# (PRD #178 M8) right before the build. `data/` is git-ignored and absent from
# the image build context, so this must run on the machine that has the manifest;
# the output is git-ignored too (never committed), so it leaves the tree clean for
# the check above while still landing in docs/research/data-audit/ to bake into
# the image (Dockerfile copies that dir → /srv/audit-data → /audit/data/*).
export_freshness() {
  log "export freshness.json from data/manifest.json"
  "${PYTHON}" "${REPO_ROOT}/scripts/export_freshness.py"
}

deploy_code() {
  need_fly
  require_clean_tree
  export_freshness
  # VITE_MAPTILER_KEY (Satellite basemap, the default) is baked into the SPA at
  # build. The Dockerfile carries the production key as its ARG default, so a
  # bare deploy just works — set this env var only to override with a different
  # key. Pass --build-arg ONLY when set; an empty value would clobber the
  # Dockerfile default (and an empty array trips bash 3.2 under set -u).
  if [[ -n "${VITE_MAPTILER_KEY:-}" ]]; then
    log "fly deploy --app ${FLY_APP} (MapTiler key override from env)"
    fly deploy --app "${FLY_APP}" --build-arg "VITE_MAPTILER_KEY=${VITE_MAPTILER_KEY}"
  else
    log "fly deploy --app ${FLY_APP} (Dockerfile default MapTiler key)"
    fly deploy --app "${FLY_APP}"
  fi
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

  # The PRD #130 exposure probe: an unauthenticated Range request to the
  # served composite must be REFUSED. This is the request that returned 206
  # with owner PII before the forward_auth gate — it must never again. (No
  # -f: a 401/403 is the *expected* outcome, not a curl failure. The
  # authenticated 206 path is pinned by tests/test_caddy_serving.py.)
  code="$(curl -sS -r 0-3 -o /dev/null -w '%{http_code}' \
    "${APP_URL}/data/processed/composite/index.json")" || die "data probe request failed"
  [[ "${code}" == "401" || "${code}" == "403" ]] \
    || die "expected 401/403 on unauthenticated data request, got ${code} — PII GATE IS OPEN"
  log "data unauth  -> ${code} (gated)"

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
