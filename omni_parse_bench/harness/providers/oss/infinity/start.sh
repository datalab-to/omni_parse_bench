#!/usr/bin/env bash
# vLLM serves $MODEL on 8000 with the model card's flags (Pro across two GPUs, Flash on one); server.py
# answers on $PORT once vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
case "$MODEL" in
    infly/Infinity-Parser2-Pro) REVISION=b27d470100514329fc6439aada8f16ccea5f9e2a
        SPLIT=(--tensor-parallel-size 2 --mm-encoder-tp-mode data) ;;
    infly/Infinity-Parser2-Flash) REVISION=cfddc4106b0abc4706f05575a164f7dd35d09c46; SPLIT=() ;;
    *) echo "MODEL is $MODEL; set it to infly/Infinity-Parser2-Pro or infly/Infinity-Parser2-Flash" >&2; exit 1 ;;
esac
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$MODEL" --revision "$REVISION" --served-model-name "$MODEL" \
    "${SPLIT[@]}" --trust-remote-code --reasoning-parser qwen3 --gpu-memory-utilization 0.85 \
    --max-model-len 65536 --mm-processor-cache-type shm --enable-prefix-caching --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/infinity/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
