"""PP-StructureV3's server: steps 1 to 4 of providers/pp_structurev3.py, with PaddleOCR's own pipeline.

`parse` says what the server answers and how it runs.
"""
from __future__ import annotations

import base64
import contextlib
import importlib.metadata
import os
import tempfile
import threading

from fastapi import FastAPI, Header, HTTPException
from model_pins import MODELS
from pydantic import BaseModel, ConfigDict

KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("furniture",)
DEVICE = os.environ.get("DEVICE", "cpu")
_LOCK = threading.Lock()
_pipeline = None
# What it serves, in every reply: the pipeline's models at the commits the image holds (model_pins.py), and
# the package whose version names the pipeline.
SERVED = {"weights": ", ".join(f"PaddlePaddle/{name}@{sha}" for name, sha in MODELS.items()),
          "revision": f"paddleocr=={importlib.metadata.version('paddleocr')}"}


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _pipeline
    from paddleocr import PPStructureV3

    # Note: no option but the device: every other setting is the pipeline's default.
    _pipeline = PPStructureV3(device=DEVICE)
    yield


app = FastAPI(lifespan=lifespan)


class Settings(BaseModel):
    """Every request sets these, from the adapter's options (the vendor's values by default)."""

    model_config = ConfigDict(extra="forbid")
    furniture: bool


class Page(BaseModel):
    page: str
    suffix: str
    settings: Settings


@app.get("/health")
def health() -> dict:
    return {"ready": _pipeline is not None}


@app.get("/served")
def served() -> dict:
    return SERVED


@app.post("/parse")
def parse(page: Page, authorization: str | None = Header(default=None)) -> dict:
    """PaddleOCR's `PPStructureV3` pipeline at its documented defaults, on the file's first page; how a page
    is processed is set out step by step in the adapter's docstring. One pipeline per uvicorn worker, reading
    one page at a time.

        GET  /health    {"ready": true} once the pipeline is loaded
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's, "settings": {"furniture"}}
                        -> the pipeline's result for the page (`parsing_res_list`: each block's label, box in
                        the pixels of the page turned upright, and content), "width" and "height" of that
                        page, "angle" (the document orientation classifier's: 0, 90, 180 or 270, or -1),
                        its markdown ("furniture" off: the pipeline's default, which leaves out the labels
                        its `markdown_ignore_labels` names), and "vendor": the package versions
    """
    if KEY and authorization != f"Bearer {KEY}":
        raise HTTPException(401, "a bearer token (OPB_ENDPOINT_KEY) is needed")
    # Note: the markdown drops number, footnote, header, header_image, footer, footer_image and aside_text by
    # default (PaddleOCR's `markdown_ignore_labels`); with `furniture` on, none is dropped, so the page's
    # headers and footers are kept.
    ignore = {"markdown_ignore_labels": []} if page.settings.furniture else {}
    with tempfile.NamedTemporaryFile(suffix=page.suffix) as f:
        f.write(base64.b64decode(page.page))
        f.flush()
        with _LOCK:
            res = next(iter(_pipeline.predict(f.name, **ignore)))
    out = res.json["res"]
    # Note: the pipeline turns a page upright (its document orientation classifier) before it reads it; its
    # boxes are on that upright page, and "angle" says how far it was turned (-1 when it was not classified).
    out["angle"] = (out.get("doc_preprocessor_res") or {}).get("angle")
    for heavy in ("layout_det_res", "overall_ocr_res", "doc_preprocessor_res"):
        out.pop(heavy, None)
    out["markdown"] = res.markdown["markdown_texts"]
    out["vendor"] = {p: importlib.metadata.version(p) for p in ("paddleocr", "paddlex", "paddlepaddle")}
    return {**out, "served": SERVED}
