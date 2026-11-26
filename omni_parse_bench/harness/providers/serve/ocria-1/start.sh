#!/usr/bin/env bash
# vLLM serves OCRia-1 on $PORT with the flags of its model card (huggingface.co/llamaindex/OCRia-1, Quickstart):
#   vllm serve llamaindex/OCRia-1 --served-model-name ocria-1 --max-model-len 32768 \
#     --limit-mm-per-prompt '{"image": 1}'
# OPB_ENDPOINT_KEY, if set, is vLLM's API key: /v1 then needs it as the bearer token.
set -euo pipefail
if [ -n "${OPB_ENDPOINT_KEY:-}" ]; then export VLLM_API_KEY="$OPB_ENDPOINT_KEY"; fi
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=llamaindex/OCRia-1}"
: "${REVISION:=489f5fa8f63858545368b9aff44256bbea6e46bc}"
export WEIGHTS REVISION
# Note: the vision encoder's attention is vLLM's own choice (the card's), except on Blackwell (compute capability
# 10 and up), where the other Qwen3.5 providers here (ovisocr2, ovisocr3, xiaomi_ocr) found vLLM 0.22.1's choice (FA4,
# compiled at start-up by the CuTe DSL) failing at initialization, so torch SDPA is used. It is the vision encoder's
# kernel alone. Not measured for OCRia-1 on vLLM 0.30.0: MM_ENCODER_ATTN_BACKEND=default turns it off.
# --- encoder attention
if [ -z "${MM_ENCODER_ATTN_BACKEND:-}" ]; then
    cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)
    if [ "${cc:-0}" -ge 10 ]; then MM_ENCODER_ATTN_BACKEND=TORCH_SDPA; else MM_ENCODER_ATTN_BACKEND=default; fi
    echo "compute capability major ${cc:-unknown}: vision-encoder attention ${MM_ENCODER_ATTN_BACKEND}" >&2
fi
ENC=()
[ "$MM_ENCODER_ATTN_BACKEND" = default ] || ENC=(--mm-encoder-attn-backend "$MM_ENCODER_ATTN_BACKEND")
# --- end encoder attention
# Note: the card's --served-model-name is ocria-1; here it is `<weights>@<revision>`, as every vLLM-alone folder
# serves it, so opb reads what answered off /v1/models.
exec /opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name "$WEIGHTS@$REVISION" --max-model-len 32768 \
    --limit-mm-per-prompt '{"image": 1}' "${ENC[@]}" --host 0.0.0.0 --port "${PORT:-8001}"
