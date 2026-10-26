#!/usr/bin/env bash
# vLLM serves the VLM on 8000 with the flags PaddleOCR documents for its vllm-server backend; server.py
# answers on $PORT once the pipeline is loaded. Either exiting stops the container.
set -euo pipefail
export PADDLE_PDX_CACHE_HOME="${PADDLE_PDX_CACHE_HOME:-${HF_HOME:-/root/.cache/huggingface}/paddlex}"
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=PaddlePaddle/PaddleOCR-VL-1.6}"
: "${REVISION:=c5630abae1d940eafe0697512a0325494b02ab42}"
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" \
    --revision "$REVISION" --served-model-name paddleocr-vl --trust-remote-code \
    --max-num-batched-tokens 16384 --no-enable-prefix-caching --mm-processor-cache-gb 0 \
    --gpu-memory-utilization 0.8 --trust-request-mm-kwargs --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
# Note: 4 workers, one pipeline each, each reading one page at a time.
/opt/paddle/bin/uvicorn server:app --app-dir /srv --host 0.0.0.0 --port "${PORT:-8001}" --workers 4 &
SERVER=$!
wait -n "$VLLM" "$SERVER"
