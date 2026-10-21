#!/usr/bin/env bash
# vLLM serves $WEIGHTS on 8000 with the model card's flags (Pro across two GPUs, Flash on one); server.py
# answers on $PORT once vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS picks the model (Pro, the published one, by default) and REVISION its checkpoint; the defaults are
# the pinned weights opb's numbers come from, so a run's record names the weights that answered. The model's
# flags depend on which it is, so weights it doesn't know are refused.
: "${WEIGHTS:=infly/Infinity-Parser2-Pro}"
case "$WEIGHTS" in
    infly/Infinity-Parser2-Pro) : "${REVISION:=b27d470100514329fc6439aada8f16ccea5f9e2a}"
        SPLIT=(--tensor-parallel-size 2 --mm-encoder-tp-mode data) ;;
    infly/Infinity-Parser2-Flash) : "${REVISION:=cfddc4106b0abc4706f05575a164f7dd35d09c46}"; SPLIT=() ;;
    *) echo "WEIGHTS is $WEIGHTS; this server knows infly/Infinity-Parser2-Pro and infly/Infinity-Parser2-Flash" >&2
        exit 1 ;;
esac
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" --served-model-name infinity-parser2 \
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
