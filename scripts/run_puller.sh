#!/usr/bin/env bash
# Launch the Pilot Data Puller desktop app.
#
# Usage:
#   ./scripts/run_puller.sh
#
# Activates the project's .venv (if present) and runs the app module.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "${HERE}/.." && pwd)"

cd "${ROOT}"

if [[ -d ".venv" ]]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec python -m app_puller "$@"
