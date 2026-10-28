#!/usr/bin/env bash
# SoMark's supervisor starts D-FINE, vLLM and the OXR API on loopback; server.py answers on $PORT once all three
# pass the supervisor's own health check. Either exiting stops the container.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=SoMarkAI/OXR-1.0}"
: "${REVISION:=c708407f9d2b4df658f2543d9132b62bb7221df4}"
export WEIGHTS REVISION
# The supervisor takes the model repository as a folder: its weights, chat template, vLLM plugin and layout model.
MODEL_PATH="$(python3 -c 'import sys; from huggingface_hub import snapshot_download as d; print(d(sys.argv[1], revision=sys.argv[2]))' "$WEIGHTS" "$REVISION")"
export MODEL_PATH
/opt/oxr-venv/bin/python /app/docker/allinone_entrypoint.py &
OXR=$!
until /opt/oxr-venv/bin/python /app/docker/allinone_entrypoint.py --healthcheck 2> /dev/null; do
    kill -0 "$OXR" 2>/dev/null || { echo 'the OXR supervisor exited' >&2; exit 1; }
    sleep 5
done
/opt/oxr-venv/bin/python /srv/server.py --port "${PORT:-8001}" &
SERVER=$!
wait -n "$OXR" "$SERVER"
