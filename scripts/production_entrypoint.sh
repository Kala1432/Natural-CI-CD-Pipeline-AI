#!/bin/sh
set -eu

flask --app backend.app db upgrade

exec gunicorn \
  --bind "0.0.0.0:${PORT:-5000}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --threads "${GUNICORN_THREADS:-4}" \
  --timeout "${GUNICORN_TIMEOUT:-120}" \
  --access-logfile - \
  --error-logfile - \
  "backend.app:create_app()"
