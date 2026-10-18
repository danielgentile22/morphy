#!/bin/sh
# DEMO_MODE refuses to boot without the read-only demo credential (ADR-077);
# the seed is idempotent, so it runs on every start.
set -e
case "$(printf '%s' "${DEMO_MODE:-}" | tr '[:upper:]' '[:lower:]')" in
  1 | true | yes | on) python -m app.demo_seed ;;
esac
exec uvicorn app.main:app --host 127.0.0.1 --port 8000
