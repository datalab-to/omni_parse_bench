"""MiniCPM-OCR SDK behind OPB's /health, /served and /parse protocol; vLLM listens on loopback."""
from __future__ import annotations

import base64
import contextlib
import os
import tempfile
import threading
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict, Field

SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}
KEY = os.environ.get("OPB_ENDPOINT_KEY")
_LOCK = threading.Lock()
_pipeline = None


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _pipeline
    from minicpmvocr.layouts.download import ensure_layout_model
    from paddlex.inference.utils.io import PDFReader
    from worker import Pipeline

    # PaddleX constructs this even for image inputs. Fail readiness if its optional PDF deps are absent.
    PDFReader(zoom=2.0)

    # The SDK verifies this official archive's SHA256 before installing it. Keep it in the shared cache.
    os.environ["OCR_LAYOUT_MODEL_DIR"] = str(ensure_layout_model(
        Path(os.environ.get("HF_HOME", "/root/.cache/huggingface")) / "minicpm-ocr" / "PP-DocLayoutV3_infer"))
    _pipeline = Pipeline()
    try:
        yield
    finally:
        _pipeline.close()
        _pipeline = None


app = FastAPI(lifespan=lifespan)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    region_workers: int = Field(ge=1)


class Page(BaseModel):
    model_config = ConfigDict(extra="forbid")
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
    if KEY and authorization != f"Bearer {KEY}":
        raise HTTPException(401, "a bearer token (OPB_ENDPOINT_KEY) is needed")
    if page.suffix not in {".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"}:
        raise HTTPException(400, f"unsupported page suffix: {page.suffix!r}")
    with tempfile.TemporaryDirectory(prefix="minicpm-ocr-") as folder:
        root = Path(folder)
        source = root / f"input{page.suffix}"
        try:
            source.write_bytes(base64.b64decode(page.page, validate=True))
        except ValueError as exc:
            raise HTTPException(400, "page must be base64-encoded") from exc
        try:
            with _LOCK:
                result = _pipeline.recognize(source, root, page.settings.region_workers)
        except Exception as exc:
            raise HTTPException(500, f"MiniCPM-OCR: {type(exc).__name__}: {exc}"[:8000]) from exc
        return {**result, "served": SERVED}
