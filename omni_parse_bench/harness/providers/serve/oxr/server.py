"""OXR-1.0's server: one page to SoMark's own parsing API (its /v1/parse/sync), its answer as it gives it.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

API = f"http://127.0.0.1:{os.environ.get('OXR_API_PORT', '8000')}/v1/parse/sync"
KEY = os.environ.get("OPB_ENDPOINT_KEY")
SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}
# Note: everything the API defaults, but page furniture, which it drops unless asked; opb scores it as
# layout.
FORM = {"api_key": "opb", "output_formats": ["markdown", "json"],
        "feature_config": json.dumps({"keep_header_footer": True})}
# Note: the API holds a page for as long as its layout and recognition retries take; opb's budget bounds
# the call.
TIMEOUT = httpx.Timeout(None, connect=10.0)

# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def parse(data: bytes, suffix: str) -> tuple[int, dict]:
    """The API's status and answer for one page file: on success its `outputs` (Markdown and its JSON pages)
    and `metadata`, else the error it gave."""
    r = httpx.post(API, data=FORM, files={"file": (f"input{suffix}", data)}, timeout=TIMEOUT)
    if r.status_code != 200:
        return r.status_code, {"error": f"OXR API: HTTP {r.status_code}: {r.text[:500]}"}
    body = r.json()
    # Note: the API answers a failure with HTTP 200 and a code: 1133 for a parameter it refused (a bug of
    # ours), any other for the page failing in the pipeline (a model call that timed out, a page it couldn't
    # decode).
    if body.get("code"):
        error = f"OXR API {body['code']}: {body.get('message')}"
        return 400 if body["code"] == 1133 else 500, {"error": error}
    return 200, {"outputs": body["data"]["result"]["outputs"], "metadata": body["data"]["metadata"],
                 "warnings": body.get("warnings", [])}


class Handler(BaseHTTPRequestHandler):
    """SoMark's OXR API (github.com/SoMarkAI/OXR at the Dockerfile's commit), its pipeline and defaults
    unchanged but for page furniture, in front of the D-FINE layout service and vLLM, which its supervisor
    runs (start.sh).

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's, "settings": {}}
                        -> {"outputs": {"markdown", "json": {"pages": [{page_size, blocks}]}}, "metadata",
                        "warnings"}

    A client error keeps its HTTP status."""
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
            if body["suffix"] not in SUFFIXES:
                return self._send(400, {"error": f"unsupported page suffix: {body['suffix']!r}"})
            if body.get("settings"):
                return self._send(400, {"error": f"OXR takes no settings, got {body['settings']!r}"})
            status, out = parse(base64.b64decode(body["page"], validate=True), body["suffix"])
            self._send(status, {**out, "served": SERVED})
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
