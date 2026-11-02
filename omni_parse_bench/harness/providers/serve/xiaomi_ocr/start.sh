#!/usr/bin/env bash
set -euo pipefail
: "${WEIGHTS:=xiaomi-research/Xiaomi-OCR-0}"
: "${REVISION:=bbd8cf8d21f256b3644b44cb860f3a7cecb93c30}"
export WEIGHTS REVISION
# Same Qwen3.5 runtime as OvisOCR2. Use the portable encoder kernel on Blackwell,
# where vLLM 0.22.1's default CuTe DSL encoder kernel fails at initialization.
if [ -z "${MM_ENCODER_ATTN_BACKEND:-}" ]; then
    cc=$(nvidia-smi --query-gpu=compute_cap --format=csv,noheader 2>/dev/null | head -1 | cut -d. -f1)
    if [ "${cc:-0}" -ge 10 ]; then MM_ENCODER_ATTN_BACKEND=TORCH_SDPA; else MM_ENCODER_ATTN_BACKEND=default; fi
fi
ENC=()
[ "$MM_ENCODER_ATTN_BACKEND" = default ] || ENC=(--mm-encoder-attn-backend "$MM_ENCODER_ATTN_BACKEND")
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name xiaomi_ocr --tensor-parallel-size 1 --gpu-memory-utilization 0.8 \
    --dtype bfloat16 --generation-config vllm "${ENC[@]}" \
    --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/client/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
