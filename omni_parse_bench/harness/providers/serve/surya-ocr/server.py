"""Surya OCR 2's server: steps 1 to 4 of providers/surya_ocr.py, with the `surya-ocr` package's code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from PIL import Image
from surya.inference import SuryaInferenceManager
from surya.input.load import load_from_file
from surya.recognition import RecognitionPredictor

KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("dpi",)
# Note: the vendor's renderer (pdfium, PyMuPDF) isn't thread-safe, and its own tools load one page at a
# time; requests arrive on many threads, so pages load one at a time here too.
LOAD = threading.Lock()
VERSION = importlib.metadata.version("surya-ocr")
_local = threading.local()


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def predictor() -> RecognitionPredictor:
    """One predictor per thread, attached to the vLLM server."""
    if getattr(_local, "predictor", None) is None:
        _local.predictor = RecognitionPredictor(SuryaInferenceManager())
    return _local.predictor


def load(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """The page as the `surya_ocr` command loads it for recognition: `load_from_file` at `dpi` for a PDF
    (the command's is the package's IMAGE_DPI_HIGHRES), the image as it is otherwise."""
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        images, _ = load_from_file(f.name, [0], dpi)
    return images[0]


def page(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """`load`, one page at a time."""
    with LOAD:
        return load(data, suffix, dpi)


def parse(data: bytes, suffix: str, s: dict) -> dict:
    result = predictor()([page(data, suffix, s["dpi"])], full_page=True)[0]
    return {**result.model_dump(mode="json"), "vendor": {"surya-ocr": VERSION}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """What the package's `surya_ocr` command does per page, around the vLLM serving the model; how a page is
    processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's, "settings": {"dpi"}}
                        -> the package's result for the page (its `model_dump`), with "vendor": the
                        surya-ocr version
    """
    def do_GET(self):
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/parse":
            return self._send(404, {"error": f"no route {self.path}"})
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"})
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(200, {**parse(base64.b64decode(body["page"]), body["suffix"], settings(body)),
                             "served": SERVED})
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
            self._send(500, {"error": f"surya failed: {type(exc).__name__}: {exc}"[:500]})

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
