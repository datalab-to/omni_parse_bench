"""chandra-ocr-2's server: steps 1 to 4 of providers/chandra_ocr.py, with the `chandra-ocr` package's code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import io
import json
import os
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from bs4 import BeautifulSoup
from chandra.input import load_image, load_pdf_images
from chandra.model.util import detect_repeat_token, scale_to_fit
from chandra.output import parse_html
from chandra.prompts import PROMPT_MAPPING
from PIL import Image

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "chandra")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("temperature", "top_p", "max_tokens", "dpi", "max_retries")
# Note: the vendor's renderer (pdfium, PyMuPDF) isn't thread-safe, and its own tools load one page at a
# time; requests arrive on many threads, so pages load one at a time here too.
LOAD = threading.Lock()
# Note: the package is installed from git, so pip's record of where it came from names the commit.
COMMIT = (json.loads(importlib.metadata.distribution("chandra-ocr").read_text("direct_url.json") or "{}")
          .get("vcs_info", {}).get("commit_id"))


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def ask(png: bytes, temperature: float, top_p: float, max_tokens: int, deadline: float) -> dict:
    """One chat completion at these settings."""
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    content = [{"type": "image_url", "image_url": {"url": url}},
               {"type": "text", "text": PROMPT_MAPPING["ocr_layout"]}]
    body = {"model": MODEL, "max_tokens": max_tokens, "temperature": temperature, "top_p": top_p,
            "messages": [{"role": "user", "content": content}]}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=max(1.0, deadline - time.monotonic()))
    r.raise_for_status()
    return r.json()


def text(completion: dict) -> str:
    return (((completion.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""


def finish(completion: dict) -> str | None:
    return (completion.get("choices") or [{}])[0].get("finish_reason")


def blocks(said: str) -> list[dict]:
    """Each top-level block: its label, its inner HTML as written, and `parse_html`'s reading of it."""
    out = []
    for div in BeautifulSoup(said, "html.parser").find_all("div", recursive=False):
        out.append({"label": div.get("data-label"), "raw": div.decode_contents(),
                    "html": parse_html(str(div), include_headers_footers=True, include_images=True)})
    return out


def load(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """The page as the package loads it: a PDF through `load_pdf_images` at `dpi` (form fields flattened
    into the page), an image through `load_image`."""
    with tempfile.NamedTemporaryFile(suffix=suffix) as f:
        f.write(data)
        f.flush()
        if suffix.lower() == ".pdf":
            return load_pdf_images(f.name, page_range=[0], image_dpi=dpi)[0]
        return load_image(f.name)


def page(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """`load`, one page at a time."""
    with LOAD:
        return load(data, suffix, dpi)


def parse(data: bytes, suffix: str, s: dict) -> dict:
    """One page: loaded and prepared as the package does it, the model asked until a reply stands, its
    blocks read. The settings `s` set the first attempt's sampling; a retry follows the package's
    schedule."""
    buf = io.BytesIO()
    scale_to_fit(page(data, suffix, s["dpi"])).save(buf, format="PNG")
    deadline, kept, usage = time.monotonic() + TIMEOUT_S, None, {"prompt_tokens": 0, "completion_tokens": 0}
    for attempt in range(s["max_retries"] + 1):
        temperature, top_p = ((min(0.2 * attempt, 0.8), 0.95) if attempt
                              else (s["temperature"], s["top_p"]))
        try:
            kept = ask(buf.getvalue(), temperature, top_p, s["max_tokens"], deadline)
        except httpx.TimeoutException:
            raise
        except httpx.HTTPError:
            if attempt == s["max_retries"]: raise
            continue
        for k in usage: usage[k] += (kept.get("usage") or {}).get(k) or 0
        said = text(kept)
        repeat = detect_repeat_token(said) or (len(said) > 50 and detect_repeat_token(said, cut_from_end=50))
        if not repeat and finish(kept) != "length": break
    return {"completion": kept, "attempts": attempt + 1, "usage": usage,
            "blocks": blocks(text(kept)), "vendor": {"chandra-ocr": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """The package's file loading, `scale_to_fit`, prompt, retry rule and `parse_html`, around the vLLM
    serving the model; how a page is processed is set out step by step in the adapter's docstring.
    `parse_html` reads each top-level block on its own, so the adapter can treat picture blocks its own way;
    concatenated, the blocks are the package's page, but for the names it gives images (a hash of the HTML it
    was given).

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "top_p", "max_tokens" (the first attempt's), "dpi",
                        "max_retries"}}
                        -> {"completion": the kept chat completion, "attempts", "usage": summed over
                        attempts, "blocks": [{"label", "raw": the block's inner HTML as the model wrote it,
                        "html": parse_html of the block}], "vendor": {"chandra-ocr": its commit}}"""
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
