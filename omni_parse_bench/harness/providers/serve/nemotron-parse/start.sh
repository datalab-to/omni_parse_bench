#!/usr/bin/env bash
# The weights at the pinned revision; vLLM serves them on 8000 with the model card's flags (docs/serving.md,
# the reference H100 profile); server.py answers on $PORT once vLLM is up. Either exiting stops the
# container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint, as in every serve folder; the Dockerfile's REVISION is the default.
: "${WEIGHTS:=nvidia/Nemotron-3.5-Parse}"
export WEIGHTS REVISION
W="${HF_HOME:-/root/.cache/huggingface}/$(basename "$WEIGHTS")-${REVISION:0:7}"
hf download "$WEIGHTS" --revision "$REVISION" --local-dir "$W" \
    --exclude 'reference/parsebench/*' --exclude 'reference/multilingual/*' > /dev/null
vllm serve "$W" --served-model-name nemotron-parse --trust-remote-code --dtype bfloat16 \
    --distributed-executor-backend uni --tensor-parallel-size 1 --data-parallel-size 1 \
    --max-model-len 16384 --max-num-seqs 192 --max-num-batched-tokens 16384 --no-enable-prefix-caching \
    --limit-mm-per-prompt '{"image":1}' --attention-config '{"flash_attn_version":3}' \
    --chat-template "$W/chat_template.jinja" --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
python3 /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
