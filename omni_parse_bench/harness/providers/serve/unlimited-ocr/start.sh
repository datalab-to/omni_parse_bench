#!/usr/bin/env bash
# vLLM serves Unlimited-OCR on 8000 with its recipe's flags (its n-gram logits processor, no prefix cache);
# server.py answers on $PORT once vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=baidu/Unlimited-OCR}"
: "${REVISION:=07dea832e22aefee32ad281d4b80551282e1c168}"
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name baidu/Unlimited-OCR --trust-remote-code \
    --logits_processors vllm.model_executor.models.unlimited_ocr:NGramPerReqLogitsProcessor \
    --no-enable-prefix-caching --mm-processor-cache-gb 0 --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
PYTHONPATH=/opt/unlimited /opt/vllm-python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
