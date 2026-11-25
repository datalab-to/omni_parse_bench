#!/usr/bin/env bash
# Downloads Dolphin-v2 (the README's `huggingface-cli download ByteDance/Dolphin-v2 --local-dir ./hf_model`),
# then server.py answers on $PORT, loading it as `demo_page.py --model_path ./hf_model` does.
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=ByteDance/Dolphin-v2}"
: "${REVISION:=c37c62768c644bb594da4283149c627765aa80f3}"
export WEIGHTS REVISION
cd /app/Dolphin
MODEL_PATH="$(python - <<PY
import os
from huggingface_hub import snapshot_download
print(snapshot_download(repo_id=os.environ["WEIGHTS"], revision=os.environ["REVISION"]))
PY
)"
export MODEL_PATH
exec python /srv/server.py --port "${PORT:-8001}"
