"""Unlimited-OCR's server: steps 1, 3 and 4 of providers/unlimited.py, with its repository's code and recipe.

The page loaded as its own pipeline loads one (github.com/baidu/Unlimited-OCR at 92ad94b, infer.py, MIT;
imported from the clone in the image), then asked as its vLLM recipe asks it, of the vLLM serving the
model; how a page is processed is set out step by step in the adapter's docstring.

    GET  /health    200 once up
    POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                    "settings": {"temperature", "top_p", "max_tokens", "dpi", "ngram_size",
                    "window_size"}}
                    -> {"completion": the model's chat completion, "model",
                    "vendor": {"Unlimited": its commit}}

With OPB_ENDPOINT_KEY set, a request needs it as its bearer token. It runs in this folder's image, beside
the vLLM serving the model (start.sh); the Dockerfile says how to build and run it.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

import infer

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
MODEL = "baidu/Unlimited-OCR"
# The vLLM recipe's request (recipes.vllm.ai/baidu/Unlimited-OCR): the prompt before the image.
PROMPT = "<image>document parsing."
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's Config (the vendor's values by default).
SETTINGS = SAMPLING + ("dpi", "ngram_size", "window_size")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
COMMIT = subprocess.run(["git", "-C", os.path.dirname(infer.__file__), "rev-parse", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
# Note: PyMuPDF isn't thread-safe, and the pipeline renders one document at a time; requests arrive on
# many threads, so pages load one at a time here too.
LOAD = threading.Lock()


def image_part(data: bytes, suffix: str, dpi: int) -> dict:
    """The page as the pipeline sends it: a PDF through its `pdf_to_images` (at `dpi`, PyMuPDF), an image
    as it is, each through its `encode_image`."""
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "page" + suffix)
        with open(path, "wb") as f:
            f.write(data)
        if suffix.lower() == ".pdf":
            with LOAD:
                path = infer.pdf_to_images(path, dpi=dpi)[0]
        return infer.encode_image(path)


def parse(data: bytes, suffix: str, s: dict) -> dict:
    content = [{"type": "text", "text": PROMPT}, image_part(data, suffix, s["dpi"])]
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            **{k: s[k] for k in SAMPLING}, "skip_special_tokens": False,
            "vllm_xargs": {"ngram_size": s["ngram_size"], "window_size": s["window_size"]}}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    return {"completion": r.json(), "model": MODEL, "vendor": {"Unlimited": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
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
