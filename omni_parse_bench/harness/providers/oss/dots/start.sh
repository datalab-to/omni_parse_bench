#!/usr/bin/env bash
# vLLM serves dots.mocr on 8000 with the flags its repository documents; server.py answers on $PORT once
# vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
/opt/vllm-python -m vllm.entrypoints.cli.main serve rednote-hilab/dots.mocr --revision e539fbb52280393adc081b289ec597430a0f9031 \
    --served-model-name rednote-hilab/dots.mocr --trust-remote-code \
    --chat-template-content-format string --gpu-memory-utilization 0.9 --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/vllm-python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
