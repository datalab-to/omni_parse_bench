"""Indra OCR's server: steps 1 to 4 of providers/indra_ocr.py, with the `indra-ocr` package's code.

What the package's `indra-ocr` command does per page: its `Converter` reads the file, the PDF's text
layer where it passes the package's checks and OCR elsewhere, and writes the page's markdown and layout
blocks. As the package's own `convert_many` runs, each page is read by one single-threaded worker process
of a pool, one worker per core; how a page is processed is set out step by step in the adapter's
docstring.

    GET  /health    200 once up
    POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                     "settings": {"mode", "math", "dpi", "furniture"}}
                    -> the page's markdown, text, blocks, source, note, rotation, skew and timings,
                    "image_size": the page as read [width, height] in pixels before any turn, and
                    "vendor": the indra-ocr version and the models' repository and revision

The models are the ones the package names (its models.py), downloaded once when it starts, as the package
downloads them. With OPB_ENDPOINT_KEY set, a request needs it as its bearer token. The Dockerfile says how
to build and run it.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import json
import multiprocessing
import os
import tempfile
from concurrent.futures import ProcessPoolExecutor
from concurrent.futures.process import BrokenProcessPool
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: every request sets these, from the adapter's Config (the vendor's values by default).
SETTINGS = ("mode", "math", "dpi", "furniture")
_converters: dict = {}


def converter(s: dict):
    """One single-threaded Converter per worker and settings, as `convert_many` gives each worker."""
    import indra_ocr

    key = tuple(s[k] for k in SETTINGS)
    if key not in _converters:
        _converters[key] = indra_ocr.load(threads=1, dpi=float(s["dpi"]), mode=s["mode"],
                                          furniture=s["furniture"], math=s["math"])
    return _converters[key]


def size(conv, path: Path) -> list[int]:
    """The page as the Converter reads it, [width, height] in pixels: a PDF's first page at the
    Converter's `page_scale`, an image as it is."""
    import pypdfium2 as pdfium
    from indra_ocr import pipeline

    if not pipeline.is_pdf(path):
        h, w = pipeline.read_images(path)[0].shape[:2]
        return [w, h]
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[0]
        k = conv.page_scale(page)
        w, h = page.get_size()
        return [round(w * k), round(h * k)]
    finally:
        doc.close()


def read(data: bytes, suffix: str, s: dict) -> dict:
    """The page through the package's `Converter.convert`, its first page; in a worker process."""
    conv = converter(s)
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        _, page = next(conv.convert(f.name, max_pages=1))
        frame = size(conv, Path(f.name))
    if page.source == "error":
        raise RuntimeError(f"the page couldn't be read: {page.note}")
    return {"markdown": page.markdown, "text": page.text, "blocks": page.blocks, "source": page.source,
            "note": page.note, "rotation": page.rotation, "skew": page.skew, "timings": page.timings,
            "image_size": frame}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    pool: ProcessPoolExecutor
    vendor: dict

    def do_GET(self):
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/parse":
            return self._send(404, {"error": f"no route {self.path}"})
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"})
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            page = base64.b64decode(body["page"])
            got = self.pool.submit(read, page, body["suffix"], settings(body)).result()
            self._send(200, {**got, "vendor": self.vendor})
        except BrokenProcessPool as exc:
            # Note: a pool that lost a worker (killed for memory, say) fails every later page at once, so
            # the server stops: a page read after that would be a failure of the server, not of the model.
            self._send(500, {"error": f"indra-ocr failed: {type(exc).__name__}: {exc}"[:500]})
            os._exit(1)
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
            self._send(500, {"error": f"indra-ocr failed: {type(exc).__name__}: {exc}"[:500]})

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
    cores = len(os.sched_getaffinity(0))
    ap.add_argument("--workers", type=int, default=int(os.environ.get("WORKERS") or cores),
                    help="worker processes, one page each at a time (default: WORKERS, else one per usable "
                         "core); each loads its own models, the math models too when a request asks for math")
    a = ap.parse_args()
    import indra_ocr
    from indra_ocr import models

    # Note: every model file, the math models too, downloaded here before the first page, so no page's
    # time goes to a download; the workers find them in the cache.
    indra_ocr.model_dir(math=True)
    Handler.vendor = {"indra-ocr": importlib.metadata.version("indra-ocr"),
                      "models": f"{models.HF_REPO}@{models.HF_REVISION}"}
    Handler.pool = ProcessPoolExecutor(a.workers, mp_context=multiprocessing.get_context("spawn"))
    ThreadingHTTPServer(("0.0.0.0", a.port), Handler).serve_forever()
