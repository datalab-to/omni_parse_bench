#!/usr/bin/env bash
# The weights at revision 47644ecc with the repository's previous config.json (revision 3d3cbc9e): the
# current one targets transformers 5 and doesn't load correctly in vLLM 0.18.1. vLLM serves them on
# 8000 with the repository's flags; server.py answers on $PORT once vLLM is up. Either exiting stops the
# container.
set -euo pipefail
# Note: WEIGHTS and REVISION are those pinned weights, so a run's record names the weights that answered. The
# config.json swap below is for that revision alone, so any other weights or revision are refused.
: "${WEIGHTS:=tencent/HunyuanOCR}"
: "${REVISION:=47644ecc4fc854efa4f505155158831f36773ee4}"
if [ "$WEIGHTS" != tencent/HunyuanOCR ] || [ "$REVISION" != 47644ecc4fc854efa4f505155158831f36773ee4 ]; then
    echo "WEIGHTS@REVISION is $WEIGHTS@$REVISION; this server patches tencent/HunyuanOCR@47644ecc4fc854efa4f505155158831f36773ee4 alone" >&2
    exit 1
fi
export WEIGHTS REVISION
W="${HF_HOME:-/root/.cache/huggingface}/hunyuan-${REVISION:0:8}"
if [ ! -f "$W/.ready" ]; then
    /venv/bin/hf download "$WEIGHTS" --revision "$REVISION" \
        --exclude 'v1.0/*' 'dflash/*' --local-dir "$W"
    /venv/bin/hf download "$WEIGHTS" config.json --revision 3d3cbc9ebde3bd08cfb70fa8b3c40466319e4b15 --local-dir "$W.cfg"
    cp "$W.cfg/config.json" "$W/config.json" && touch "$W/.ready"
fi
/venv/bin/vllm serve "$W" --served-model-name tencent/HunyuanOCR -tp 1 --limit-mm-per-prompt '{"image":4,"video":0}' \
    --trust-remote-code --gpu-memory-utilization 0.9 --max-model-len 131072 --max-num-batched-tokens 131072 \
    --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/venv/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
