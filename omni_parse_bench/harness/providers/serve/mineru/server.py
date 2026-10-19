"""MinerU2.5-Pro's server: steps 1 to 4 of providers/mineru.py, with MinerU's own code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import io
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from docvortex.document.pdf.images import load_images_from_pdf_core
from mineru_vl_utils import MinerUClient
from mineru_vl_utils.post_process import json2md
from mineru_vl_utils.vlm_client.base_client import HttpResponseError
from PIL import Image

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000")
KEY = os.environ.get("OPB_ENDPOINT_KEY")
VERSION = importlib.metadata.version("mineru-vl-utils")
_client: MinerUClient | None = None
_lock = threading.Lock()


def client() -> MinerUClient:
    """One client shared by the threads, as it holds the HTTP pool and the model's name; made on the
    first page, as making it asks vLLM for that name."""
    global _client
    with _lock:
        if _client is None:
            _client = MinerUClient(backend="http-client", server_url=VLLM, use_tqdm=False, max_retries=0)
        return _client


def page(data: bytes, suffix: str) -> Image.Image:
    """The page as MinerU loads it: a PDF through docvortex's `load_images_from_pdf_core` (200 DPI, the
    long edge at most 3500 px), an image as it is."""
    if suffix.lower() == ".pdf":
        return load_images_from_pdf_core(data, start_page_id=0, end_page_id=0)[0]["img_pil"]
    return Image.open(io.BytesIO(data)).convert("RGB")


def parse(data: bytes, suffix: str) -> dict:
    found = [dict(b) for b in client().two_step_extract(page(data, suffix))]
    return {"blocks": found, "markdown": json2md(found), "vendor": {"mineru-vl-utils": VERSION}}


class Handler(BaseHTTPRequestHandler):
    """MinerU's page render (its docvortex package) and its client's two-step extraction and `json2md`, around
    the vLLM serving the model; how a page is processed is set out step by step in the adapter's docstring.
    The client is made on the first page, as making it asks vLLM for the model's name.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's}
                        -> {"blocks": the client's blocks {type, bbox, angle, content}, boxes from 0 to 1,
                        "markdown": json2md of them, "vendor"}

    A client error keeps its HTTP status. With OPB_ENDPOINT_KEY set, a request needs it as its bearer token.
    It runs in this folder's image, beside the vLLM serving the model (start.sh); the Dockerfile says how to
    build and run it.
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
            self._send(200, parse(base64.b64decode(body["page"]), body["suffix"]))
        except httpx.TimeoutException as exc:
            self._send(504, {"error": f"vLLM timed out: {exc}"})
        except HttpResponseError as exc:
            self._send(exc.status_code, {"error": str(exc)[:500]})
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
