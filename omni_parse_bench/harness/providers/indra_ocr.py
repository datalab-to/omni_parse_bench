"""Indra OCR (datalab-to/indra-ocr), served from providers/serve/indra/ on any host; it needs no GPU.

Run as the `indra-ocr` package (0.3.2) runs it with its `indra-ocr` command, with the models it names.
Steps 1 to 4 run on the server (serve/indra/server.py); step 5 runs here, with no vendor code.

How a page is processed:

  1. Input loading        opb sends the page file. The package's `Converter.convert` reads it: a PDF
                          page's text layer is read where it passes the package's checks (mode `auto`),
                          and the page is rendered at 200 DPI (lower for a page past its pixel limit)
                          for the rest; an image file is read as it is.
  2. Image preprocessing  the package's own: the page turned upright and straightened.
  3. Model inference      ONNX Runtime, one single-threaded worker process per core, as its
                          `convert_many` runs: line detection, the recognizer (another for lines
                          with Chinese characters), and the reading-order and layout model; with
                          `math` on, a classifier finds the lines that hold math and a math
                          recognizer reads them as text with inline LaTeX.
  4. Vendor output parsing  the package's `Page`: its markdown (headings, lists, tables as HTML) and
                          its layout blocks in reading order, each with a label, a box in the pixels
                          of the page turned upright, and its text.
  5. Mapping to opb outputs  html is the markdown through `markdown.to_html`; blocks are each block's
                          label (LABELS) and box divided by the upright page's size, then turned back
                          onto the page as sent (`layout.unturned`).

Differences from the vendor:

  - math is read as LaTeX (`math` on, its `--math`; the package's default is off, which reads math as
    plain text);
  - page headers and footers are kept in the markdown (`furniture`; the package leaves them out by
    default), as every other adapter keeps them; and
  - each page has the benchmark's 900 s.

    docker build -t opb-indra omni_parse_bench/harness/providers/serve/indra
    docker run -p 8001:8001 opb-indra
    opb predict --provider indra-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path

from ... import markdown
from .. import contract, errors, http, layout

SUPPORTS = frozenset({"html", "blocks"})
# Note: the package names its models (a tag of datalab-to/indra-ocr), so its version decides them; the
# server's answer says which it loaded.
PACKAGE = "indra-ocr==0.3.2"
# Indra OCR's block classes (its order_post.BLOCK_CLASSES, chandra's labels) onto views.LABELS.
LABELS = {
    "Text": "text", "Table-Of-Contents": "text", "Section-Header": "heading", "Page-Header": "page_furniture",
    "Page-Footer": "page_furniture", "List-Group": "list", "Caption": "caption", "Footnote": "footnote",
    "Table": "table", "Form": "form",
}


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the Indra OCR server (serve/indra/) answers, and how its Converter reads a page (the
    package's defaults, but math read as LaTeX and headers and footers kept)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    mode: str = dataclasses.field(default="auto", metadata={
        "help": "auto reads a PDF's text layer where it passes the checks and OCRs elsewhere; ocr never "
                "reads it; text reads it even when the checks fail"})
    math: bool = dataclasses.field(default=True, metadata={
        "help": "write math as LaTeX (slower); off reads it as plain text"})
    dpi: int = 200
    furniture: bool = dataclasses.field(default=True, metadata={"help": "keep page headers and footers"})


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"package": PACKAGE, "settings": http.settings(config),
            "page": "the file, read by its Converter"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The page's markdown as html, its blocks on the page as sent. A label LABELS lacks fails the
    blocks only."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        md = raw.get("markdown")
        outputs["html"] = markdown.to_html(md if md is not None else raw["text"])
    if "blocks" in request.outputs:
        turned = raw.get("rotation") or 0
        w, h = raw["image_size"]
        upright = (h, w) if turned % 180 else (w, h)
        try:
            blocks = [layout.block(layout.label(LABELS, b["label"]), b["bbox"], upright,
                                   " ".join(b["text"].split())) for b in raw["blocks"]]
            outputs["blocks"] = [x | {"bbox": layout.unturned(x["bbox"], turned)} for x in blocks]
        except errors.VendorError as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
