#!/usr/bin/env bash
# vLLM serves Nanonets-OCR2-3B on $PORT with no other flags, as its model card does.
# OPB_ENDPOINT_KEY, if set, is vLLM's API key: /v1 then needs it as the bearer token.
set -euo pipefail
if [ -n "${OPB_ENDPOINT_KEY:-}" ]; then export VLLM_API_KEY="$OPB_ENDPOINT_KEY"; fi
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
exec /opt/vllm-python -m vllm.entrypoints.cli.main serve nanonets/Nanonets-OCR2-3B --revision c3886ff00bb037ce7da24988c9eafaf1fe2bed72 \
    --served-model-name nanonets/Nanonets-OCR2-3B --host 0.0.0.0 --port "${PORT:-8001}"
