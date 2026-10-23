"""PaddleOCR-VL's server: steps 1 to 4 of providers/paddleocr_vl.py, with its own pipeline.

`parse` says what the server answers and how it runs.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.metadata
import os
import tempfile
import threading
import time

import httpx
from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

VLM_URL = f"http://127.0.0.1:{os.environ.get('VLM_PORT', '8000')}"
KEY = os.environ.get("OPB_ENDPOINT_KEY")
_LOCK = threading.Lock()
_pipeline = None


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def wait_for_vlm(limit_s: float = 30 * 60) -> None:
    deadline = time.monotonic() + limit_s
    while time.monotonic() < deadline:
        with contextlib.suppress(httpx.HTTPError):
            if httpx.get(f"{VLM_URL}/health", timeout=5).status_code == 200: return
        time.sleep(2)
    raise RuntimeError("vLLM never came up")


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _pipeline
    from paddleocr import PaddleOCRVL

    wait_for_vlm()
    _pipeline = PaddleOCRVL(pipeline_version="v1.6", vl_rec_backend="vllm-server",
                            vl_rec_server_url=f"{VLM_URL}/v1", vl_rec_api_model_name="paddleocr-vl",
                            device="cpu")
    yield


app = FastAPI(lifespan=lifespan)


class Settings(BaseModel):
    """Every request sets these, from the adapter's options (the vendor's values by default)."""

    model_config = ConfigDict(extra="forbid")
    dpi: int


class Page(BaseModel):
    page: str
    suffix: str
    settings: Settings


def load(path: str, suffix: str, dpi: int):
    """The page as the pipeline's batch sampler hands it on: a PDF through the reader it makes (PaddleX's
    PDFReader, at `dpi`; the sampler's is PDF_RENDER_SCALE, 2.0, i.e. 144 DPI), loaded and then read to
    its end, as the sampler does (reading releases PaddleX's pdfium lock, which inside `predict`
    concurrent pages wait on); an image file as its path, for the pipeline's own image reader."""
    from paddlex.inference.utils.io import PDFReader
    from paddlex.inference.utils.pdf_rendering import DEFAULT_MAX_IMAGE_PIXELS

    if suffix.lower() != ".pdf":
        return path
    reader = PDFReader(zoom=dpi / 72, max_pixels=DEFAULT_MAX_IMAGE_PIXELS)
    # Note: `read` of a path would take PaddleX's pdfium lock (not reentrant) and then wait for it in
    # `load`; the sampler loads first too.
    return list(reader.read(reader.load(path)))[0]


def size(path: str, suffix: str, img) -> tuple[int, int]:
    """(width, height) of the page as loaded: the rendered PDF page, or the image as stored, its EXIF
    rotation applied, as the pipeline's image reader opens it."""
    from PIL import Image, ImageOps

    if suffix.lower() == ".pdf":
        return int(img.shape[1]), int(img.shape[0])
    return ImageOps.exif_transpose(Image.open(path)).size


@app.get("/health")
def health() -> dict:
    return {"ready": _pipeline is not None}


@app.get("/served")
def served() -> dict:
    return SERVED


@app.post("/parse")
def parse(page: Page, authorization: str | None = Header(default=None)) -> dict:
    """PaddleOCR's `PaddleOCRVL` pipeline (pipeline_version v1.6, the VLM through its vllm-server backend),
    beside the VLM's vLLM server; how a page is processed is set out step by step in the adapter's docstring.
    One pipeline per uvicorn worker, reading one page at a time.

        GET  /health    {"ready": true} once the pipeline is loaded
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's, "settings": {"dpi"}}
                        -> the pipeline's result for the page (`parsing_res_list`: each block's label, box
                        in the pixels of the page as loaded, and content), "width" and "height" of that
                        page, its markdown with every block kept, and "vendor": the package versions
    """
    if KEY and authorization != f"Bearer {KEY}":
        raise HTTPException(401, "a bearer token (OPB_ENDPOINT_KEY) is needed")
    with tempfile.NamedTemporaryFile(suffix=page.suffix) as f:
        f.write(base64.b64decode(page.page))
        f.flush()
        with _LOCK:
            img = load(f.name, page.suffix, page.settings.dpi)
            (res,) = list(_pipeline.predict(img, markdown_ignore_labels=[]))
        w, h = size(f.name, page.suffix, img)
    out = res.json["res"]
    out.pop("layout_det_res", None)
    out["height"], out["width"] = h, w
    res["model_settings"]["markdown_ignore_labels"] = []
    out["markdown"] = res._to_markdown(pretty=True)["markdown_texts"]
    out["vendor"] = {p: importlib.metadata.version(p) for p in ("paddleocr", "paddlex", "paddlepaddle")}
    return {**out, "served": SERVED}
