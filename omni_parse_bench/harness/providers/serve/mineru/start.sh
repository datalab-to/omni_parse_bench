#!/usr/bin/env bash
# vLLM serves MinerU2.5-Pro on 8000 as mineru-vl-utils' README serves it (its logits processor); server.py
# answers on $PORT once vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=opendatalab/MinerU2.5-Pro-2605-1.2B}"
: "${REVISION:=08aaea840498d49ce16247b6263196cf02814885}"
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" \
    --revision "$REVISION" --logits-processors mineru_vl_utils:MinerULogitsProcessor \
    --gpu-memory-utilization 0.85 --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/vllm-python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
