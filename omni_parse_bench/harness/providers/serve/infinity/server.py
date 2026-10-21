"""Infinity-Parser2's server: steps 1 to 4 of providers/infinity.py, with its `infinity_parser2` SDK's code.

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
from infinity_parser2.prompts import PROMPT_DOC2JSON
from infinity_parser2.utils.image import encode_image_to_base64, load_image
from infinity_parser2.utils.pdf import convert_pdf_to_images
from infinity_parser2.utils.utils import (
    convert_json_to_markdown,
    extract_json_content,
    truncate_last_incomplete_element,
)
from PIL import Image

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("WEIGHTS", "infly/Infinity-Parser2-Pro")
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = SAMPLING + ("dpi", "min_pixels", "max_pixels")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: the vendor's renderer (pdfium, PyMuPDF) isn't thread-safe, and its own tools load one page at a
# time; requests arrive on many threads, so pages load one at a time here too.
LOAD = threading.Lock()
VERSION = importlib.metadata.version("infinity_parser2")


def load(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """The page as the SDK loads it: a PDF through `convert_pdf_to_images` at `dpi`, an image as it is."""
    if suffix.lower() == ".pdf":
        return convert_pdf_to_images(data, dpi=dpi)[0]
    return load_image(Image.open(io.BytesIO(data)))


def page(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """`load`, one page at a time."""
    with LOAD:
        return load(data, suffix, dpi)


def parse(data: bytes, suffix: str, s: dict) -> dict:
    b64, _ = encode_image_to_base64(page(data, suffix, s["dpi"]), min_pixels=s["min_pixels"],
                                    max_pixels=s["max_pixels"])
    buf = io.BytesIO()
    Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB").save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    content = [{"type": "image_url", "image_url": {"url": url}}, {"type": "text", "text": PROMPT_DOC2JSON}]
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            **{k: s[k] for k in SAMPLING}, "chat_template_kwargs": {"enable_thinking": False}}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    completion = r.json()
    said = ((completion.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    out = {"completion": completion, "model": MODEL, "vendor": {"infinity_parser2": VERSION}}
    if said.strip():
        read, _ = truncate_last_incomplete_element(extract_json_content(said))
        out |= {"json": read, "markdown": convert_json_to_markdown(read, keep_header_footer=True)}
    return out


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """The SDK's file loading, image encoding, prompt and reading, around the vLLM serving the model; how a
    page is processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "top_p", "max_tokens", "dpi", "min_pixels", "max_pixels"}}
                        -> {"completion": the model's chat completion, "json": the reply as the SDK reads
                        it, "markdown": the page, "model", "vendor"}; an empty reply gives no "json" or
                        "markdown"
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
