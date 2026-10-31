#!/usr/bin/env bash
# vLLM serves the weights on 8000 with the model card's flags; server.py answers on $PORT once vLLM is up.
# Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION are the pinned weights opb's numbers come from, so a run's record names the
# weights that answered; others are served by naming both (docker run -e WEIGHTS=... -e REVISION=...).
: "${WEIGHTS:=ATH-MaaS/OvisOCR2}"
: "${REVISION:=cbdede82e048659b83310476ff807da825f8fe78}"
export WEIGHTS REVISION
# Note: the vision encoder's attention is vLLM's own choice (the model card's), except on Blackwell (compute capability
# 10 and up): there vLLM 0.22.1's choice (FA4, compiled at start-up by the CuTe DSL) fails with "mlir_global_dtors()
# missing 1 required positional argument: 'data'" (measured on a B200, driver 570), so torch SDPA is used. It is the
# vision encoder's kernel alone; the language model's attention is untouched. MM_ENCODER_ATTN_BACKEND names a backend
# (or `default`) and overrides this choice.
# --- encoder attention
if [ -z "${MM_ENCODER_ATTN_BACKEND:-}" ]; then
    cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)
    if [ "${cc:-0}" -ge 10 ]; then MM_ENCODER_ATTN_BACKEND=TORCH_SDPA; else MM_ENCODER_ATTN_BACKEND=default; fi
    echo "compute capability major ${cc:-unknown}: vision-encoder attention ${MM_ENCODER_ATTN_BACKEND}" >&2
fi
ENC=()
[ "$MM_ENCODER_ATTN_BACKEND" = default ] || ENC=(--mm-encoder-attn-backend "$MM_ENCODER_ATTN_BACKEND")
# --- end encoder attention
# Note: --generation-config vllm, because the card's offline `LLM` takes its sampling from its own
# SamplingParams alone, so no generation_config.json of the weights adds defaults of its own.
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name ovisocr2 --tensor-parallel-size 1 --gpu-memory-utilization 0.8 \
    --gdn-prefill-backend triton --generation-config vllm "${ENC[@]}" \
    --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/ovis/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
