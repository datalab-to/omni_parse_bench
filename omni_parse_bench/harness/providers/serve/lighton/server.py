"""LightOnOCR-3's server: steps 1 to 4 of providers/lighton.py, with its `lightonocr` client's code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import io
import json
import math
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from lightonocr.client import to_data_url
from lightonocr.grounding import GROUNDING_PROMPT
from lightonocr.postprocess import fix_escaped_dollars
from PIL import Image

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("MODEL", "lightonai/LightOnOCR-3-4B")
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = SAMPLING + ("dpi", "max_pixels")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: the client is installed from git, so pip's record of where it came from names the commit.
COMMIT = (json.loads(importlib.metadata.distribution("lightonocr").read_text("direct_url.json") or "{}")
          .get("vcs_info", {}).get("commit_id"))


def render(pdf: bytes, dpi: int, max_pixels: int) -> Image.Image:
    """A PDF page as LightOn's benchmark renders it.

    Copied and adapted, not imported: it lives in the repository's benchmarks/ (Apache-2.0), in a class
    tied to its benchmark harness, not in the `lightonocr` package.
    benchmarks/ocr_bench/providers/loocr_grounding.py at 36755d4, `_pdf_to_images_with_size`: poppler at
    `dpi`, lowered so the page fits `max_pixels` before it is rasterized, then shrunk if poppler's
    rounding still overshoots."""
    from pdf2image import convert_from_bytes
    from pypdf import PdfReader

    box = PdfReader(io.BytesIO(pdf)).pages[0].cropbox
    w_in, h_in = abs(float(box.width)) / 72, abs(float(box.height)) / 72
    dpi = min(dpi, math.floor(math.sqrt(max_pixels / (w_in * h_in))))
    img = convert_from_bytes(pdf, dpi=dpi, first_page=1, last_page=1)[0]
    if img.width * img.height > max_pixels:
        scale = math.sqrt(max_pixels / (img.width * img.height))
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    return img


def parse(data: bytes, suffix: str, s: dict) -> dict:
    pdf = suffix.lower() == ".pdf"
    img = render(data, s["dpi"], s["max_pixels"]) if pdf else Image.open(io.BytesIO(data))
    content = [{"type": "image_url", "image_url": {"url": to_data_url(img, None)}},
               {"type": "text", "text": GROUNDING_PROMPT}]
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            **{k: s[k] for k in SAMPLING}, "chat_template_kwargs": {"enable_thinking": False}}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    completion = r.json()
    said = ((completion.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    return {"completion": completion, "text": fix_escaped_dollars(said), "model": MODEL,
            "vendor": {"lightonocr": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """Its benchmark's page render, then its client's request and repair of the reply, around the vLLM serving
    the model; how a page is processed is set out step by step in the adapter's docstring. The client
    returns only the reply's text, so this asks with its pieces, to keep the reply's finish reason and usage.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "top_p", "max_tokens", "dpi", "max_pixels"}}
                        -> {"completion": the model's chat completion, "text": its content repaired,
                        "model", "vendor": {"lightonocr": the client's commit}}

    With OPB_ENDPOINT_KEY set, a request needs it as its bearer token. It runs in this folder's image,
    beside the vLLM serving the model (start.sh); the Dockerfile says how to build and run it.
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
            self._send(200, parse(base64.b64decode(body["page"]), body["suffix"], settings(body)))
        except httpx.TimeoutException as exc:
            self._send(504, {"error": f"vLLM timed out: {exc}"})
        except httpx.HTTPStatusError as exc:
            self._send(502, {"error": f"vLLM answered {exc.response.status_code}: {exc.response.text[:300]}"})
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
