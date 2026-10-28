#!/usr/bin/env bash
# Recognition on loopback; the SDK's page pipeline on $PORT. Either exiting stops both.
set -euo pipefail
: "${WEIGHTS:=openbmb/MiniCPM-OCR-1.0}"
: "${REVISION:=a59a4acf215e34c6d73149e9eafdb88ed2086e39}"
export WEIGHTS REVISION
export CUDA_HOME
CUDA_HOME="$(/opt/minicpm/.venv-vllm/bin/python -c 'import sysconfig; print(sysconfig.get_path("purelib") + "/nvidia/cu13")')"
# FlashInfer JIT launches ninja as a subprocess; the vendor installs it in this venv.
export PATH="/opt/minicpm/.venv-vllm/bin:$CUDA_HOME/bin:$PATH"
VLLM=""
SERVER=""
cleanup() {
    if [[ -n "$SERVER" ]]; then kill "$SERVER" 2>/dev/null || true; fi
    if [[ -n "$VLLM" ]]; then kill "$VLLM" 2>/dev/null || true; fi
}
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
/opt/minicpm/.venv-vllm/bin/vllm serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name minicpm-ocr --dtype bfloat16 --trust-remote-code \
    --host 127.0.0.1 --port 8000 --max-model-len 40960 --max-num-batched-tokens 40960 \
    --max-num-seqs 32 --limit-mm-per-prompt '{"image":36,"video":0}' \
    --attention-backend FLASH_ATTN --mm-encoder-attn-backend FLASH_ATTN \
    --mm-processor-kwargs '{"downsample_mode":"4x"}' --gpu-memory-utilization 0.85 \
    --trust-request-mm-kwargs --default-chat-template-kwargs '{"enable_thinking":false}' &
VLLM=$!
until curl -sf http://127.0.0.1:8000/health > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo 'vLLM exited' >&2; exit 1; }
    sleep 5
done
# Four persistent pipelines, one page at a time each, as in PaddleOCR-VL's server.
/opt/sdk/bin/uvicorn server:app --app-dir /srv --host 0.0.0.0 --port "${PORT:-8001}" --workers 4 &
SERVER=$!
wait -n "$VLLM" "$SERVER"
