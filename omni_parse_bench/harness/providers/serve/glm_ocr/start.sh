#!/usr/bin/env bash
# vLLM serves GLM-OCR on 8000 as the SDK's README documents (MTP speculation, 3 tokens; the README says
# to set the memory share per machine, and 0.5 leaves room for the SDK's layout model); server.py starts
# the SDK servers and answers on $PORT. Either exiting stops the container.
set -euo pipefail
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
/opt/vllm-python -m vllm.entrypoints.cli.main serve zai-org/GLM-OCR --revision 2e85a62840ccac27daa451df36c736c4636b8628 \
    --speculative-config '{"method": "mtp", "num_speculative_tokens": 3}' --served-model-name glm-ocr \
    --gpu-memory-utilization 0.5 --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/glm/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
