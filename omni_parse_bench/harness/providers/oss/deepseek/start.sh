#!/usr/bin/env bash
# The weights at a pinned revision (cached in HF_HOME), then server.py on $PORT: it loads the engine
# before it listens.
set -euo pipefail
# Note: the weights at a pinned revision, so a run's record names the weights that answered.
export DEEPSEEK_WEIGHTS="$(/usr/bin/python3 -c "from huggingface_hub import snapshot_download as s
print(s('deepseek-ai/DeepSeek-OCR-2', revision='aaa02f3811945a91062062994c5c4a3f4c0af2b0'))")"
exec /usr/bin/python3 /srv/server.py --port "${PORT:-8001}"
