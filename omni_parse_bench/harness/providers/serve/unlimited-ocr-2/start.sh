#!/usr/bin/env bash
# The vendor's SGLang serves Unlimited-OCR 2 on 8000 with its model card's environment and flags; server.py
# answers on $PORT once SGLang is up. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=baidu/Unlimited-OCR-2}"
: "${REVISION:=5632329a32e103d5f1add270681e0f5c1233c6e4}"
export WEIGHTS REVISION
export SGLANG_UOCR_EANABLE_DOC_LIMIT=1 SGLANG_UOCR_DOC_GUNDAM_PAGE_WINDOW=10 SGLANG_UOCR_DOC_BASE_PAGE_WINDOW=10
export SGLANG_UOCR_MAX_PAGE_TOKENS=20000 SGLANG_OPT_UOCR_SAM_REL_POS_BIAS_MB=64
export SGLANG_UOCR_SHM_WRAP_MODEL_DATA=1 SGLANG_UOCR_SHM_WRAP_MIN_MB=1 SGLANG_VLM_CACHE_SIZE_MB=0
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
/venv/bin/python -m sglang.launch_server --model-path "$WEIGHTS" --revision "$REVISION" \
    --served-model-name baidu/Unlimited-OCR-2 --chat-template unlimited-ocr \
    --tokenizer-backend fastokens --tokenizer-worker-num 8 --mem-fraction-static 0.7 \
    --max-running-requests 64 --max-prefill-tokens 2048 --enable-custom-logit-processor \
    --enable-streaming-session --allow-auto-truncate --disable-radix-cache --mm-preprocess-cache-size-mb 0 \
    --cuda-graph-backend-decode full --cuda-graph-max-bs-decode 64 --cuda-graph-backend-prefill full \
    --cuda-graph-max-bs-prefill 16384 --cuda-graph-bs-prefill 1024 2048 \
    --cuda-graph-config '{"prefill": {"backend": "full", "full_prefill_max_req": 64}}' \
    --host 127.0.0.1 --port 8000 &
SGLANG=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$SGLANG" 2>/dev/null || { echo "sglang exited" >&2; exit 1; }
    sleep 5
done
/venv/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$SGLANG" "$SERVER"
