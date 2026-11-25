"""Dolphin-v2's server: steps 1 to 4 of providers/dolphin_v2.py, with Dolphin's own code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, "/app/Dolphin")  # the repository's demo_page.py and utils/

from demo_page import DOLPHIN, process_single_image  # noqa: E402
from PIL import Image  # noqa: E402
from utils.markdown_utils import MarkdownConverter  # noqa: E402
from utils.utils import convert_pdf_to_images, setup_output_dirs  # noqa: E402

MODEL_PATH = os.environ.get("MODEL_PATH", "/app/Dolphin/hf_model")
KEY = os.environ.get("OPB_ENDPOINT_KEY")
# The README's `--max_batch_size`, default 4 (`demo_page.py`'s argument): elements decoded in parallel.
MAX_BATCH_SIZE = 4
_model: DOLPHIN | None = None
# Note: one page at a time: the model is shared, and its batches are the parallelism the repository uses.
_lock = threading.Lock()

# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def parse(data: bytes, suffix: str) -> dict:
    """What `demo_page.py` does for one file: a PDF through `convert_pdf_to_images` (the page's long edge
    896 px, its default), an image as `Image.open(...).convert("RGB")`; then `process_single_image`
    (stage 1, the layout and reading order; stage 2, each element by type) and `MarkdownConverter` (its
    default, without `--post_process`)."""
    global _model
    with _lock, tempfile.TemporaryDirectory() as work:
        if _model is None:
            _model = DOLPHIN(MODEL_PATH)
        path = os.path.join(work, f"page{suffix}")
        with open(path, "wb") as f:
            f.write(data)
        if suffix.lower() == ".pdf":
            if not (images := convert_pdf_to_images(path)):
                raise ValueError("the PDF could not be converted to an image")
            image = images[0].convert("RGB")
        else:
            image = Image.open(path).convert("RGB")
        setup_output_dirs(work)
        _, elements = process_single_image(image, _model, work, "page", MAX_BATCH_SIZE,
                                           save_individual=False, post_process=False)
        markdown = MarkdownConverter(False).convert(elements)
    return {"elements": elements, "markdown": markdown, "image_size": list(image.size)}


class Handler(BaseHTTPRequestHandler):
    """Dolphin-v2's page parse; how a page is processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's}
                        -> {"elements": the repository's results {label, bbox, text, reading_order, tags},
                        boxes in the image's pixels, "markdown": the .md it writes, "image_size": [w, h],
                        "served"}

    An error is a 500 with its message."""
    def do_GET(self):
        if self.path == "/served": return self._send(200, SERVED)
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/parse":
            return self._send(404, {"error": f"no route {self.path}"})
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"})
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(200, {**parse(base64.b64decode(body["page"]), body["suffix"]), "served": SERVED})
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"[:500]})

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ThreadingHTTPServer(("0.0.0.0", ap.parse_args().port), Handler).serve_forever()
