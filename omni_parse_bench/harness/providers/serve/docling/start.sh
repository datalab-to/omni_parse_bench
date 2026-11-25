#!/usr/bin/env bash
# server.py answers on $PORT with one converter per uvicorn worker (WORKERS, docker run -e, sets how many; each
# loads its own models). No vLLM and no GPU: Docling runs on the CPU here.
set -euo pipefail
exec uvicorn server:app --app-dir /srv --host 0.0.0.0 --port "${PORT:-8001}" --workers "${WORKERS:-2}"
