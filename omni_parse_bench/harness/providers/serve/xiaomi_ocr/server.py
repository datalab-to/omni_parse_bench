"""Xiaomi whole-page inference and vendor post-processing, behind the opb HTTP contract."""
from __future__ import annotations

import argparse
import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

from vendor.document import finalize_document

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
SETTINGS = ("temperature", "top_p", "presence_penalty", "repetition_penalty", "max_tokens")
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}
PROMPT = ('Extract all information from the main body of the document image and represent it '
          'in markdown format, ignoring headers and footers. Tables should be expressed in OTSL '
          'format, formulas in the document should be represented using LATEX format, and the '
          'parsing should be organized according to the reading order.')


def parse(png: bytes, s: dict) -> dict:
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    body = {"model": "xiaomi_ocr", **s,
            "messages": [{"role": "user", "content": [{"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": url}}]}],
            "chat_template_kwargs": {"enable_thinking": False}}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    completion = r.json()
    choice = completion["choices"][0]
    text = (choice["message"]["content"] or "").strip()
    if not text:
        raise ValueError("empty model response")
    return {"text": finalize_document(text), "finish_reason": choice.get("finish_reason"),
            "completion": completion}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """The vendor's request and post-processing, around the vLLM serving the model; how a page is processed is
    set out step by step in the adapter's docstring.

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 image file, "suffix", "settings": {"temperature", "max_tokens",
                        "top_p", "presence_penalty", "repetition_penalty"}}
                        -> {"text": the cleaned reply, "finish_reason",
                        "completion": vLLM's reply as it came}"""
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
            self._send(200, {**parse(base64.b64decode(body["page"]), settings(body)), "served": SERVED})
        except KeyError as exc:
            self._send(400, {"error": f"{exc}"})
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
