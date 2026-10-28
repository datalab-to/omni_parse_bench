"""Unlimited-OCR 2's server: steps 1, 3 and 4 of providers/unlimited_ocr2.py, with its model card's client
and its repository's post-processing.

`Handler` says what the server answers and how it runs.
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

import fitz
import httpx
import process_unlimitedOCR2
from sglang.srt.sampling.custom_logit_processor import DeepseekOCRNoRepeatNGramLogitProcessor

SGLANG = os.environ.get("SGLANG_URL", "http://127.0.0.1:8000/v1")
MODEL = "baidu/Unlimited-OCR-2"
# The model card's request for one page: the image, then the prompt, which marks the page with <PAGE>.
PROMPT = "<PAGE><image>Multi page parsing."
NGRAM = DeepseekOCRNoRepeatNGramLogitProcessor.to_str()
PAGE_TOKEN_ID = 128827  # <PAGE>, config.json's sparse_attention_config.page_token_id
EOS_TOKEN_ID = 1
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("temperature", "max_tokens", "dpi", "crop_mode", "ngram_size", "window_size", "max_page_tokens")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
COMMIT = subprocess.run(["git", "-C", os.path.dirname(process_unlimitedOCR2.__file__), "rev-parse", "HEAD"],
                        capture_output=True, text=True).stdout.strip()
# Note: PyMuPDF isn't thread-safe; requests arrive on many threads, so pages load one at a time.
LOAD = threading.Lock()


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def image_part(data: bytes, suffix: str, dpi: int) -> dict:
    """The page as the model card's client sends it: a PDF rendered at `dpi` to PNG (PyMuPDF), an image as it
    is, either one as a data URL."""
    if suffix.lower() == ".pdf":
        with LOAD, tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "page.pdf")
            with open(path, "wb") as f:
                f.write(data)
            doc = fitz.open(path)
            data, suffix = doc[0].get_pixmap(matrix=fitz.Matrix(dpi / 72, dpi / 72)).tobytes("png"), ".png"
            doc.close()
    ext = suffix.lower().lstrip(".")
    mime = "image/jpeg" if ext in ("jpg", "jpeg") else f"image/{ext}"
    url = f"data:{mime};base64,{base64.b64encode(data).decode()}"
    return {"type": "image_url", "image_url": {"url": url}}


def parse(data: bytes, suffix: str, s: dict) -> dict:
    content = [image_part(data, suffix, s["dpi"]), {"type": "text", "text": PROMPT}]
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            "temperature": s["temperature"], "max_tokens": s["max_tokens"], "skip_special_tokens": False,
            "images_config": {"crop_mode": s["crop_mode"]}, "custom_logit_processor": NGRAM,
            "custom_params": {"ngram_size": s["ngram_size"], "window_size": s["window_size"],
                              "page_token_id": PAGE_TOKEN_ID, "eos_token_id": EOS_TOKEN_ID,
                              "max_page_tokens": s["max_page_tokens"]}}
    r = httpx.post(f"{SGLANG}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    completion = r.json()
    said = completion["choices"][0]["message"]["content"] or ""
    return {"completion": completion, "markdown": process_unlimitedOCR2.convert(said), "model": MODEL,
            "vendor": {"Unlimited-OCR": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """The page loaded and asked as the model card's SGLang client does (huggingface.co/baidu/Unlimited-OCR-2
    at 5632329), of the vendor's SGLang serving the model, and the reply converted to markdown by the
    repository's `process_unlimitedOCR2.convert` (github.com/baidu/Unlimited-OCR at 48ff432, MIT; imported
    from the clone in the image); how a page is processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "max_tokens", "dpi", "crop_mode", "ngram_size",
                        "window_size", "max_page_tokens"}}
                        -> {"completion": the model's chat completion, "markdown": its conversion,
                        "model", "vendor": {"Unlimited-OCR": its commit}}
    """
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
            self._send(200, {**parse(base64.b64decode(body["page"]), body["suffix"], settings(body)),
                             "served": SERVED})
        except httpx.TimeoutException as exc:
            self._send(504, {"error": f"SGLang timed out: {exc}"})
        except httpx.HTTPStatusError as exc:
            status, text = exc.response.status_code, exc.response.text[:300]
            self._send(502, {"error": f"SGLang answered {status}: {text}"})
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
