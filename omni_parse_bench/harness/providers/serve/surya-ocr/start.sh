#!/usr/bin/env bash
# vLLM serves surya-ocr-2 on 8000 under the model id the package asks for, with the flags the package's
# launcher sets at VLLM_GPU_TYPE=h100 (MTP speculation, 2 tokens); server.py answers on $PORT once vLLM is up.
# MTP_TOKENS is how many draft tokens MTP speculation proposes (2, as the package sets); 0 serves without it.
# It changes speed only.
# Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=datalab-to/surya-ocr-2}"
: "${REVISION:=3b3d4cdf88d6928b0acdc75181b13206ea67c4a3}"
: "${MTP_TOKENS:=2}"
export WEIGHTS REVISION
SPEC=()
[ "$MTP_TOKENS" -gt 0 ] && SPEC=(--speculative-config "{\"method\": \"mtp\", \"num_speculative_tokens\": $MTP_TOKENS}")
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" \
    --revision "$REVISION" --served-model-name datalab-to/surya-ocr-2 \
    --no-enforce-eager --max-num-seqs 104 --dtype bfloat16 --max-model-len 18000 \
    --max-num-batched-tokens 16384 --gpu-memory-utilization 0.85 --enable-prefix-caching \
    --mm-processor-kwargs '{"min_pixels": 3136, "max_pixels": 6291456}' \
    "${SPEC[@]}" --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/surya/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
