#!/usr/bin/env bash
# server.py answers on $PORT with one PP-StructureV3 pipeline per uvicorn worker (WORKERS, docker run -e, sets how
# many; each loads its own models). It runs on the CPU unless DEVICE says otherwise (docker run -e DEVICE=gpu:0
# --gpus all, with a GPU build of paddlepaddle); no vLLM is used.
set -euo pipefail
exec uvicorn server:app --app-dir /srv --host 0.0.0.0 --port "${PORT:-8001}" --workers "${WORKERS:-2}"
