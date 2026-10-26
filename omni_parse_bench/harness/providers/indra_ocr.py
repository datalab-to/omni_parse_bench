"""Indra OCR (datalab-to/indra-ocr), served from providers/serve/indra-ocr/ on any host; it needs no GPU."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import contract, errors, http, layout
from ..adapter import Served

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
class IndraOcr(Served):
    """Where the Indra OCR server (serve/indra-ocr/) answers, and how its Converter reads a page (the
    package's defaults, but math read as LaTeX and headers and footers kept).

    Run as the `indra-ocr` package (0.3.2) runs it with its `indra-ocr` command, with the models it names.
    Steps 1 to 4 run on the server (serve/indra-ocr/server.py); step 5 runs here, with no vendor code.

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
        plain text); and
      - page headers and footers are kept in the markdown (`furniture`; the package leaves them out by
        default), as every other adapter keeps them.

        docker build -t opb-indra-ocr omni_parse_bench/harness/providers/serve/indra-ocr
        docker run -p 8001:8001 opb-indra-ocr
        opb init indra-ocr > config.yaml
        opb run --config config.yaml --set system.indra-ocr.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "datalab-to/indra-ocr",
                                 "revision": "v3.1.1"},
        metadata={"help": "the weights its server serves and their revision; by default its package's"})
    mode: str = dataclasses.field(default="auto", metadata={
        "help": "auto reads a PDF's text layer where it passes the checks and OCRs elsewhere; ocr never "
                "reads it; text reads it even when the checks fail"})
    math: bool = dataclasses.field(default=True, metadata={
        "help": "write math as LaTeX (slower); off reads it as plain text"})
    dpi: int = 200
    furniture: bool = dataclasses.field(default=True, metadata={"help": "keep page headers and footers"})

    name: ClassVar[str] = "indra-ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "indra-ocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: IndraOcr) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"package": PACKAGE, "settings": http.settings(config),
            "page": "the file, read by its Converter"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: IndraOcr) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def parse(raw: dict, request: contract.Request, config: IndraOcr | None = None) -> tuple[dict, dict]:
    """The page's markdown as html, its blocks on the page as sent."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        md = raw.get("markdown")
        outputs["html"] = markdown.to_html(md if md is not None else raw["text"])
    if "blocks" in request.outputs:
        turned = raw.get("rotation") or 0
        w, h = raw["image_size"]
        upright = (h, w) if turned % 180 else (w, h)
        found = raw["blocks"]
        try:
            with adapter.reading("the Converter's blocks"):
                blocks = [layout.block(layout.label(LABELS, b["label"]), b["bbox"], upright,
                                       " ".join(b["text"].split())) for b in found]
                outputs["blocks"] = [x | {"bbox": layout.unturned(x["bbox"], turned)} for x in blocks]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
