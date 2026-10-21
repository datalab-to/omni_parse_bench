#!/usr/bin/env bash
# vLLM serves Nanonets-OCR2-3B on $PORT with no other flags, as its model card does.
# OPB_ENDPOINT_KEY, if set, is vLLM's API key: /v1 then needs it as the bearer token.
set -euo pipefail
if [ -n "${OPB_ENDPOINT_KEY:-}" ]; then export VLLM_API_KEY="$OPB_ENDPOINT_KEY"; fi
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=nanonets/Nanonets-OCR2-3B}"
: "${REVISION:=c3886ff00bb037ce7da24988c9eafaf1fe2bed72}"
export WEIGHTS REVISION
exec /opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name nanonets/Nanonets-OCR2-3B --host 0.0.0.0 --port "${PORT:-8001}"
