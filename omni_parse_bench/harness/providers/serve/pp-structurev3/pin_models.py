"""Downloads each model of model_pins.py at its commit into PaddleX's model folder (`official_models/` under
PADDLE_PDX_CACHE_HOME), where PaddleX looks before it downloads anything. Run when the image is built."""
import os
from pathlib import Path

from huggingface_hub import snapshot_download
from model_pins import MODELS

home = Path(os.environ["PADDLE_PDX_CACHE_HOME"])
for name, sha in MODELS.items():
    snapshot_download(repo_id=f"PaddlePaddle/{name}", revision=sha, local_dir=home / "official_models" / name)
    print(f"{name}@{sha}")
