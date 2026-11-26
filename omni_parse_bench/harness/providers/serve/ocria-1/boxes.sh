#!/usr/bin/env bash
# OCRia-1's layout boxes (the model card's experimental `ocria_grounding`, with Docling's Heron detector) on
# $BOXES_PORT, default 8100, for the answers of the vLLM server that start.sh runs. The card's requirements:
#   pip install "transformers==5.22.2" accelerate torchvision timm scipy pypdfium2 huggingface_hub
# here in /opt/boxes, a venv over the image's own torch and torchvision, so vLLM's Transformers is untouched.
# BOXES_PYTHON picks another interpreter with them.
set -euo pipefail
: "${WEIGHTS:=llamaindex/OCRia-1}"
: "${REVISION:=489f5fa8f63858545368b9aff44256bbea6e46bc}"
export WEIGHTS REVISION
exec "${BOXES_PYTHON:-/opt/boxes/bin/python}" "$(dirname "$0")/boxes.py" --port "${BOXES_PORT:-8100}"
