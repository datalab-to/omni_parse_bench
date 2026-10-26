#!/usr/bin/env bash
# server.py answers on $PORT: it downloads the models, starts one worker process per usable core (WORKERS,
# docker run -e, sets fewer where memory is short), then serves. No vLLM: Indra OCR runs on ONNX Runtime in
# the workers.
set -euo pipefail
exec python /srv/server.py --port "${PORT:-8001}"
