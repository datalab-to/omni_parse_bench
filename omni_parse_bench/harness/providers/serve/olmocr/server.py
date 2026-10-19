"""olmOCR 2's server: steps 1 to 4 of providers/olmocr.py, with its own pipeline's code.

`parse` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import dataclasses
import os
import tempfile
import types

from aiohttp import web
from olmocr import pipeline
from olmocr.image_utils import convert_image_to_pdf_bytes

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
KEY = os.environ.get("OPB_ENDPOINT_KEY")
COMMIT = os.environ.get("OLMOCR_COMMIT")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("target_longest_image_dim", "max_page_retries")
# The pipeline's own defaults (pipeline.py, its argument parser) for its other arguments, against our
# vLLM. Note: it fires its remaining attempts in parallel when the queue of the vLLM it launched is empty;
# this vLLM isn't its own, so that count stays unknown and the attempts run one after another.
ARGS = {"server": VLLM, "model": "olmocr", "api_key": None, "guided_decoding": False}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


async def parse(data: bytes, suffix: str, s: dict) -> dict:
    """Each page goes through the pipeline's own `process_page` (github.com/allenai/olmocr at f7cfe4c,
    olmocr/pipeline.py), at its arguments' defaults but for those the request sets, against the vLLM
    serving the model; how a page is processed is set out step by step in the adapter's docstring.

        GET  /health    200 once up
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's,
                        "settings": {"target_longest_image_dim", "max_page_retries"}: pipeline arguments}
                        -> the pipeline's PageResponse fields ("natural_text", "is_rotation_valid", ...),
                        "is_valid", "is_fallback", "input_tokens", "output_tokens", "vendor"

    A page no attempt read comes back with "is_fallback": true and no text: the pipeline's last resort, the
    PDF's own text layer, is not the model reading the page. With OPB_ENDPOINT_KEY set, a request needs it
    as its bearer token. It runs in this folder's image, beside the vLLM serving the model (start.sh); the
    Dockerfile says how to build and run it.
    """
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "page" + suffix)
        with open(path, "wb") as f:
            f.write(data)
        if suffix.lower() != ".pdf":
            # Note: as the pipeline does with an image file, it is made a one-page PDF first.
            pdf = os.path.join(tmp, "page.pdf")
            with open(pdf, "wb") as f:
                f.write(convert_image_to_pdf_bytes(path))
            path = pdf
        result = await pipeline.process_page(types.SimpleNamespace(**ARGS, **s), 0, path, path, 1)
    out = dataclasses.asdict(result.response) | {
        "is_valid": result.is_valid, "is_fallback": result.is_fallback, "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens, "vendor": {"olmocr": COMMIT}}
    if result.is_fallback: out["natural_text"] = None
    return out


async def handle(request: web.Request) -> web.Response:
    if KEY and request.headers.get("Authorization") != f"Bearer {KEY}":
        return web.json_response({"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"}, status=401)
    try:
        body = await request.json()
        out = await parse(base64.b64decode(body["page"]), body["suffix"], settings(body))
        return web.json_response(out)
    except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
        return web.json_response({"error": f"{type(exc).__name__}: {exc}"[:500]}, status=500)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True})


async def startup(app: web.Application) -> None:
    # Note: main() sets this from --max_concurrent_requests (default 1600); here it is made in this loop.
    pipeline.max_concurrent_requests_limit = asyncio.BoundedSemaphore(1600)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    app = web.Application(client_max_size=64 * 1024 * 1024)
    app.on_startup.append(startup)
    app.add_routes([web.get("/health", health), web.post("/parse", handle)])
    web.run_app(app, host="0.0.0.0", port=ap.parse_args().port)
