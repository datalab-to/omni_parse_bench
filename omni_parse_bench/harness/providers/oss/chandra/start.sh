#!/usr/bin/env bash
# vLLM serves chandra-ocr-2 on 8000 with the flags of the package's own launcher (chandra/scripts/vllm.py
# at --gpu h100, MTP off as it defaults); server.py answers on $PORT once vLLM is up. Either exiting stops
# the container.
set -euo pipefail
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
/opt/vllm-python -m vllm.entrypoints.cli.main serve datalab-to/chandra-ocr-2 \
    --revision af93b47dba1b47b6640c86ccf487ed2260ab9a09 --served-model-name chandra --no-enforce-eager \
    --max-num-seqs 64 --dtype bfloat16 --max-model-len 18000 --max_num_batched_tokens 8192 \
    --gpu-memory-utilization .85 --enable-prefix-caching \
    --mm-processor-kwargs '{"min_pixels": 3136, "max_pixels": 6291456}' --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/chandra/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
