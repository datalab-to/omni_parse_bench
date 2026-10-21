#!/usr/bin/env bash
# The weights (cached in HF_HOME), then server.py on $PORT: it loads the engine before it listens.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=deepseek-ai/DeepSeek-OCR-2}"
: "${REVISION:=aaa02f3811945a91062062994c5c4a3f4c0af2b0}"
export WEIGHTS REVISION
export DEEPSEEK_WEIGHTS="$(/usr/bin/python3 -c "import os; from huggingface_hub import snapshot_download as s
print(s(os.environ['WEIGHTS'], revision=os.environ['REVISION']))")"
exec /usr/bin/python3 /srv/server.py --port "${PORT:-8001}"
