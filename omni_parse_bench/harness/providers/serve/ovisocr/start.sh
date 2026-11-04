#!/usr/bin/env bash
# vLLM serves the weights on 8000 with the model card's flags; server.py answers on $PORT once vLLM is up.
# Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION are the pinned weights opb's numbers come from, so a run's record names the
# weights that answered; others are served by naming both (docker run -e WEIGHTS=... -e REVISION=...).
: "${WEIGHTS:=ATH-MaaS/OvisOCR}"
: "${REVISION:=7b4601993131f971fb68363789ed17f55172096d}"
export WEIGHTS REVISION
# Note: --generation-config vllm, because the card's offline `LLM` takes its sampling from its own
# SamplingParams alone, so no generation_config.json of the weights adds defaults of its own.
/opt/vllm-python -m vllm.entrypoints.cli.main serve "$WEIGHTS" --revision "$REVISION" \
    --served-model-name ovisocr --tensor-parallel-size 1 --gpu-memory-utilization 0.8 \
    --trust-remote-code --generation-config vllm \
    --host 127.0.0.1 --port 8000 &
VLLM=$!
until curl -sf http://127.0.0.1:8000/v1/models > /dev/null; do
    kill -0 "$VLLM" 2>/dev/null || { echo "vllm exited" >&2; exit 1; }
    sleep 5
done
/opt/ovis/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$VLLM" "$SERVER"
