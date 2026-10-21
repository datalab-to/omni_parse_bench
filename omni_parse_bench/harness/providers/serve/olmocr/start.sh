#!/usr/bin/env bash
# vLLM serves olmOCR-2 (FP8) on 8000 as its pipeline's server does (a 16384-token context, no video);
# server.py answers on $PORT once vLLM is up. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=allenai/olmOCR-2-7B-1025-FP8}"
: "${REVISION:=40bd7202494b8264ee17ada08b401b5aab7a9ce1}"
export WEIGHTS REVISION
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" \
    --revision "$REVISION" --served-model-name olmocr --max-model-len 16384 \
    --limit-mm-per-prompt '{"video": 0}' --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
# Note: its venv's bin on the PATH, for the img2pdf command the pipeline runs.
PATH=/opt/olmocr/bin:$PATH /opt/olmocr/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
