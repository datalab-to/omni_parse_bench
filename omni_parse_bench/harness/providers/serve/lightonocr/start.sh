#!/usr/bin/env bash
# vLLM serves $WEIGHTS on 8000 with the model card's flags; server.py answers on $PORT once vLLM is up.
# Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS picks the model (the 4B, the larger, by default) and REVISION its checkpoint; the defaults are the
# pinned weights opb's numbers come from, so a run's record names the weights that answered. Weights this server
# doesn't know are refused.
: "${WEIGHTS:=lightonai/LightOnOCR-3-4B}"
case "$WEIGHTS" in
    lightonai/LightOnOCR-3-4B) : "${REVISION:=b71010f095dc3735de7ee6b9969bff8f8f50b39a}" ;;
    lightonai/LightOnOCR-3-0.8B) : "${REVISION:=36d8636925327c671bd8e479c517a004f7566bd9}" ;;
    *) echo "WEIGHTS is $WEIGHTS; this server knows lightonai/LightOnOCR-3-4B and lightonai/LightOnOCR-3-0.8B" >&2
        exit 1 ;;
esac
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" --served-model-name "$WEIGHTS" \
    --gpu-memory-utilization 0.85 --limit-mm-per-prompt '{"image": 1}' --max-model-len 24576 \
    --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/lighton/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
