#!/usr/bin/env bash
# Downloads MonkeyOCR-pro-3B (its README's `tools/download_model.py -n MonkeyOCR-pro-3B`, which is a
# Hugging Face snapshot into model_weight/), then server.py answers on $PORT, loading the model with the
# repository's model_configs.yaml (LMDeploy backend, as shipped).
set -euo pipefail
# Note: WEIGHTS and REVISION pick the checkpoint; the defaults are the pinned weights opb's numbers come from,
# so a run's record names the weights that answered.
: "${WEIGHTS:=echo840/MonkeyOCR-pro-3B}"
: "${REVISION:=913c6e24b2ef293e6384f74a3e374d0c043c9741}"
export WEIGHTS REVISION
cd /app/MonkeyOCR
python - <<PY
import os
from huggingface_hub import snapshot_download
snapshot_download(repo_id=os.environ["WEIGHTS"], revision=os.environ["REVISION"], local_dir="model_weight")
PY
exec python /srv/server.py --port "${PORT:-8001}"
