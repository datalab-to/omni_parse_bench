"""Nemotron 3.5 Parse's server: steps 3 and 4 of providers/nemotron_parse.py, with NVIDIA's own client.

The model repository's `nemotron_parse` package (`DocumentParser.parse` and its `postprocess_document`),
around the vLLM serving the model; how a page is processed is set out step by step in the adapter's
docstring. The client takes images only, so this takes the page as an image file.

    GET  /health    200 once up
    GET  /served    what it serves: {weights, revision}, as each answer says
    POST /parse     {"page": base64 image file, "suffix", "settings": {"mode": "single", "double" or
                    "triple", and the full-page request's "temperature", "top_k", "top_p",
                    "repetition_penalty", "seed", "max_tokens"}}
                    -> {"document": the client's document (markdown, blocks, raw_out, warnings),
                    "responses": each model request's finish reason and usage, "requests", "mode",
                    "image_size", "vendor"}; or, when the client raises its GenerationError,
                    {"error", "stage", "response": the failed request's reply, kept}

With OPB_ENDPOINT_KEY set, a request needs it as its bearer token. It runs in this folder's image,
beside the vLLM serving the model (start.sh); the Dockerfile says how to build and run it.
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

from PIL import Image

from nemotron_parse.inference import DocumentParser, GenerationError, GenerationSettings

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
REVISION = os.environ.get("REVISION", "")
# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS", "nvidia/Nemotron-3.5-Parse"), "revision": REVISION}
SAMPLING = ("temperature", "top_k", "top_p", "repetition_penalty", "seed", "max_tokens")
# Note: every request sets these, from the adapter's Config (the client's values by default).
SETTINGS = ("mode",) + SAMPLING
_LOCK = threading.Lock()
_PARSERS: dict[tuple, DocumentParser] = {}


def parser_for(s: dict) -> DocumentParser:
    """One client per full-page sampling; detection and crops keep the client's own defaults."""
    key = tuple(s[k] for k in SAMPLING)
    with _LOCK:
        if key not in _PARSERS:
            _PARSERS[key] = DocumentParser(VLLM, "nemotron-parse", timeout=TIMEOUT_S,
                                           fullpage=GenerationSettings(**{k: s[k] for k in SAMPLING}))
        return _PARSERS[key]


def _summary(r: dict) -> dict:
    return {"finish_reason": r.get("finish_reason"), "usage": r.get("usage") or {}}


def parse(data: bytes, s: dict) -> dict:
    with Image.open(io.BytesIO(data)) as img:
        image = img.convert("RGB")
    vendor = {"nemotron-parse": importlib.metadata.version("nemotron-parse"),
              "vllm": importlib.metadata.version("vllm"), "weights_revision": REVISION}
    try:
        doc = parser_for(s).parse(image, mode=s["mode"], triple_regions="union")
    except GenerationError as exc:
        return {"error": str(exc), "stage": exc.stage, "response": exc.response,
                "responses": [_summary(exc.response)], "mode": s["mode"], "image_size": list(image.size),
                "vendor": vendor, "served": SERVED}
    stages = doc.pop("stages")
    info = doc.pop("inference")
    detection = [stages["detection"]] if "detection" in stages else []
    responses = [stages["fullpage"], *detection, *stages["crops"]]
    return {"document": doc, "responses": [_summary(r) for r in responses], "requests": info["requests"],
            "regions": len(info["regions"]), "mode": s["mode"], "image_size": list(image.size),
            "vendor": vendor, "served": SERVED}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
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
            self._send(200, parse(base64.b64decode(body["page"]), settings(body)))
        except (KeyError, ValueError) as exc:
            self._send(400, {"error": f"{type(exc).__name__}: {exc}"[:500]})
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
            # Note: an HTTP or transport failure between the client and vLLM is the server's, so a 502,
            # which the harness retries as it retries any vendor's.
            self._send(502, {"error": f"{type(exc).__name__}: {exc}"[:500]})

    def log_message(self, *args):
        pass

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
