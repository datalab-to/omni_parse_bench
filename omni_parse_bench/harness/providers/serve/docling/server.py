"""Docling's server: steps 1 to 4 of providers/docling.py, with the `docling` package's own converter.

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
from pydantic import BaseModel, ConfigDict

KEY = os.environ.get("OPB_ENDPOINT_KEY")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = ("furniture",)
_LOCK = threading.Lock()
_converter = None
# The two Hugging Face models the pipeline loads, at exact commits. The layout model's default is `main`, so
# it is pinned here; TableFormer's is the tag v2.3.0 in the package's own code (table_structure_model.py),
# which is this commit. OCR is RapidOCR's torch backend (adapter docstring), whose models the pinned
# `rapidocr` names by its own version (ModelScope RapidAI/RapidOCR at v3.10.0), downloaded when the image is
# built.
LAYOUT = ("docling-project/docling-layout-heron", "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8")
TABLES = ("docling-project/docling-models", "fc0f2d45e2218ea24bce5045f58a389aed16dc23")
# What it serves, in every reply: those models and the package whose version names the rest.
SERVED = {"weights": ", ".join(f"{repo}@{sha}" for repo, sha in (LAYOUT, TABLES)),
          "revision": f"docling=={importlib.metadata.version('docling')}"}


def make_converter():
    """Docling's converter, as the server runs it (the Dockerfile builds it once to download the models)."""
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import ThreadedPdfPipelineOptions
    from docling.document_converter import DocumentConverter, ImageFormatOption, PdfFormatOption

    # Note: the standard pipeline's own default options (`DocumentConverter()` builds these), with one change:
    # the layout model's revision, `main` by default, is the commit in LAYOUT. Its models are in the image
    # (Dockerfile), downloaded when it was built. Their device is Docling's default, `auto` (start.sh).
    options = ThreadedPdfPipelineOptions()
    options.layout_options.model_spec = options.layout_options.model_spec.model_copy(
        update={"revision": LAYOUT[1]})
    return DocumentConverter(format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options),
                                             InputFormat.IMAGE: ImageFormatOption(pipeline_options=options)})


@contextlib.asynccontextmanager
async def lifespan(_: FastAPI):
    global _converter
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.utils.accelerator_utils import decide_device

    _converter = make_converter()
    print(f"docling device: {decide_device(AcceleratorOptions().device)}", flush=True)
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


def items(doc, layers: set) -> list[dict]:
    """The document's items in reading order: label, text, and the box on the first page in the page's own
    units, from the top left, as `[left, top, right, bottom]`. An item with no box on a page has none."""
    from docling_core.types.doc import TableItem

    out = []
    for item, _ in doc.iterate_items(included_content_layers=layers):
        provs = [p for p in item.prov if p.page_no in doc.pages]
        if not provs: continue
        page_no = provs[0].page_no
        height = doc.pages[page_no].size.height
        boxes = [p.bbox.to_top_left_origin(height) for p in provs if p.page_no == page_no]
        box = [min(b.l for b in boxes), min(b.t for b in boxes),
               max(b.r for b in boxes), max(b.b for b in boxes)]
        if isinstance(item, TableItem):
            cells = sorted(item.data.table_cells,
                           key=lambda c: (c.start_row_offset_idx, c.start_col_offset_idx))
            text = " ".join(c.text for c in cells if c.text)
        else:
            text = getattr(item, "text", "") or ""
        out.append({"label": item.label.value, "text": text, "bbox": box, "page_no": page_no,
                    "layer": item.content_layer.value})
    return out


@app.get("/health")
def health() -> dict:
    return {"ready": _converter is not None}


@app.get("/served")
def served() -> dict:
    return SERVED


@app.post("/parse")
def parse(page: Page, authorization: str | None = Header(default=None)) -> dict:
    """Docling's `DocumentConverter` (its standard PDF pipeline at its defaults) on the file's first page;
    how a page is processed is set out step by step in the adapter's docstring.
    One converter per uvicorn worker, reading one page at a time.

        GET  /health    {"ready": true} once the converter is made
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's, "settings": {"furniture"}}
                        -> the document's "html" (its HTML export) and "markdown", its "items" (each one's
                        label, text, and box from the top left in the units of "page", the first page's
                        {"width", "height"}), and "vendor": the package versions
    """
    from docling.datamodel.base_models import ConversionStatus
    from docling_core.types.doc import ContentLayer

    if KEY and authorization != f"Bearer {KEY}":
        raise HTTPException(401, "a bearer token (OPB_ENDPOINT_KEY) is needed")
    # Note: the export's default is the body only; the page's headers and footers are in its furniture layer.
    layers = {ContentLayer.BODY, ContentLayer.FURNITURE} if page.settings.furniture else {ContentLayer.BODY}
    with tempfile.NamedTemporaryFile(suffix=page.suffix) as f:
        f.write(base64.b64decode(page.page))
        f.flush()
        with _LOCK:
            result = _converter.convert(f.name, page_range=(1, 1), raises_on_error=False)
    if result.status not in (ConversionStatus.SUCCESS, ConversionStatus.PARTIAL_SUCCESS):
        raise HTTPException(500, f"docling failed: {result.status.value}: {result.errors}"[:500])
    doc = result.document
    first = doc.pages[min(doc.pages)]
    return {"html": doc.export_to_html(included_content_layers=layers),
            "markdown": doc.export_to_markdown(included_content_layers=layers),
            "items": items(doc, layers), "page": {"width": first.size.width, "height": first.size.height},
            "status": result.status.value,
            "vendor": {p: importlib.metadata.version(p) for p in ("docling", "docling-core",
                                                                  "docling-ibm-models", "docling-parse",
                                                                  "rapidocr")},
            "served": SERVED}
