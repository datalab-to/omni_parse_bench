"""dots.mocr's server: steps 1 to 4 of providers/dots.py, with its repository's own parser code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import io
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from dots_mocr.utils import doc_utils, format_transformer, image_utils, layout_utils, prompts
from PIL import Image

MODE = "prompt_layout_all_en"
PLACEHOLDER = "<|img|><|imgpad|><|endofimg|>"
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = SAMPLING + ("dpi",)
VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
MODEL = os.environ.get("VLLM_MODEL", "rednote-hilab/dots.mocr")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: the vendor's renderer (pdfium, PyMuPDF) isn't thread-safe, and its own tools load one page at a
# time; requests arrive on many threads, so pages load one at a time here too.
LOAD = threading.Lock()


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def commit() -> str | None:
    """The dots.mocr commit this server runs."""
    here = os.path.dirname(os.path.dirname(prompts.__file__))
    try:
        return subprocess.run(["git", "-C", here, "rev-parse", "HEAD"], capture_output=True, text=True,
                              check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def ask(img: Image.Image, s: dict) -> dict:
    """The model's chat completion for the image, asked as the parser asks it."""
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    body = {"model": MODEL, **{k: s[k] for k in SAMPLING}, "messages": [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": url}},
        {"type": "text", "text": PLACEHOLDER + prompts.dict_promptmode_to_prompt[MODE]}]}]}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def load(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """The page as the parser loads it: a PDF through `load_images_from_pdf` at `dpi` (its render, which
    falls back to 72 DPI past 4500 px), an image through `fetch_image`."""
    if suffix.lower() != ".pdf":
        return image_utils.fetch_image(Image.open(io.BytesIO(data)).convert("RGB"))
    with tempfile.NamedTemporaryFile(suffix=".pdf") as f:
        f.write(data)
        f.flush()
        images = doc_utils.load_images_from_pdf(f.name, dpi=dpi)
    if not images:
        raise ValueError("the parser rendered no page (it skips a page it finds unsafe or empty)")
    return images[0]


def page(data: bytes, suffix: str, dpi: int) -> Image.Image:
    """`load`, one page at a time."""
    with LOAD:
        return load(data, suffix, dpi)


def read(text: str, origin: Image.Image, image: Image.Image) -> dict:
    """The parser's reading of a reply: its cells, boxes in the pixels of `origin` (the page as loaded),
    and the page as `layoutjson2md` writes it (without the picture crops); or, when the reply's JSON
    doesn't parse, no cells and its cleaned text."""
    cells, filtered = layout_utils.post_process_output(text, MODE, origin, image)
    if filtered:
        return {"cells": None, "markdown": cells}
    ft = format_transformer
    page = [ft.get_formula_in_markdown(c.get("text") or "") if c.get("category") == "Formula"
            else ft.clean_text(c.get("text") or "") for c in cells if c.get("category") != "Picture"]
    return {"cells": cells, "markdown": "\n\n".join(page)}


def parse(data: bytes, suffix: str, s: dict) -> dict:
    """One page: loaded and prepared as the parser does it, the model asked, its reply read."""
    origin = page(data, suffix, s["dpi"])
    image = image_utils.fetch_image(origin)
    completion = ask(image, s)
    choice = (completion.get("choices") or [{}])[0]
    text = (choice.get("message") or {}).get("content") or ""
    # Note: a reply cut at the token limit is read too, as the parser reads it.
    got = read(text, origin, image) if text.strip() else {"cells": None, "markdown": ""}
    return {**got, "image_size": list(origin.size), "completion": completion, "vendor": {"dots.ocr": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """What `DotsMOCRParser` does per page (github.com/rednote-hilab/dots.mocr at 23f3e56), around the vLLM
    serving the model; how a page is processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"temperature", "top_p", "max_tokens", "dpi"}}
                        -> {"cells": [{bbox, category, text}] or null, "markdown", "image_size": [w, h] of
                        the page as loaded, "completion": the model's chat completion, "vendor"}

    Boxes are in the pixels of the page as loaded (`image_size`)."""
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


COMMIT = commit()

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ThreadingHTTPServer(("0.0.0.0", ap.parse_args().port), Handler).serve_forever()
