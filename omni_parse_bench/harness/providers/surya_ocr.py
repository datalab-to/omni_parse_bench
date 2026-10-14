"""Surya OCR 2 (datalab-to/surya-ocr-2), served from providers/oss/surya/ on any GPU host.

Run as the public `surya-ocr` package (0.22.1) runs it with its `surya_ocr` command. Steps 1 to 4 run on
the server (oss/surya/server.py); step 5 runs here, with no vendor code.

How a page is processed:

  1. Input loading        opb sends the page file. A PDF is rendered by the package's `load_from_file`
                          at IMAGE_DPI_HIGHRES, 192 DPI, the resolution its command uses for
                          recognition; an image file is opened as it is.
  2. Image preprocessing  the package's own, inside its predictor (`scale_to_fit` to its pixel limits).
  3. Model inference      vLLM 0.20.1 with the flags the package's own launcher sets at
                          VLLM_GPU_TYPE=h100 (MTP speculation, 2 tokens); one full-page call through
                          `RecognitionPredictor(full_page=True)`, at the package's prompt, sampling
                          and token limit. A page whose output loops or does not parse is asked again
                          at rising temperature, up to 6 times (SURYA_FULLPAGE_REGEN, which the package
                          calls its setting for benchmarking), then falls back, as the package does, to
                          layout plus OCR per block.
  4. Vendor output parsing  the package's result: the page as layout blocks in reading order, each
                          with a canonical label, a box in the image's pixels and its HTML.
  5. Mapping to opb outputs  html is the blocks' HTML in reading order, page headers and footers
                          kept, skipped (visual) blocks adding no text; blocks are each block's label
                          (LABELS) and box divided by the page image's size.

Differences from the vendor:

  - SURYA_FULLPAGE_REGEN is on (the package's default is off; it names it as the setting for
    benchmarking); and
  - each page has the benchmark's 900 s.

    docker build -t opb-surya omni_parse_bench/harness/providers/oss/surya
    docker run --gpus all -p 8001:8001 opb-surya
    opb predict --provider surya-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import os
import re
from pathlib import Path

from .. import budget, contract, errors, http, layout

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "datalab-to/surya-ocr-2"
PACKAGE = "surya-ocr==0.22.1"
# Surya's canonical labels (surya/layout/label.py: LAYOUT_PRED_RELABEL) onto views.LABELS, as the
# datalab adapter maps the same types. BlankPage marks an empty page and holds no block.
LABELS = {
    "Text": "text", "SectionHeader": "heading", "ListGroup": "list", "Caption": "caption",
    "Footnote": "footnote", "PageHeader": "page_furniture", "PageFooter": "page_furniture",
    "Equation": "equation", "Code": "code", "TableOfContents": "text", "Bibliography": "text",
    "Table": "table", "Form": "form",
    "Picture": "figure", "Figure": "figure", "Diagram": "figure", "ChemicalBlock": "figure",
}
_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the Surya OCR 2 server (oss/surya/) answers, and the DPI a PDF is loaded at (the
    `surya_ocr` command's, IMAGE_DPI_HIGHRES, by default)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    dpi: int = 192


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "package": PACKAGE, "mode": "RecognitionPredictor(full_page=True)",
            "fullpage_regen": True,
            "settings": http.settings(config), "page": "the file, loaded as its surya_ocr command loads one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    body = {**http.page(page), "settings": http.settings(config)}
    return contract.Call(http.post(f"{config.base_url.rstrip('/')}/parse", body, budget.Budget(timeout),
                                   key=os.environ.get("OPB_ENDPOINT_KEY")))


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The page in reading order, and its blocks. A label LABELS lacks fails the blocks only."""
    blocks = sorted(raw.get("blocks") or [], key=lambda b: b.get("reading_order", 0))
    _, _, w, h = raw.get("image_bbox") or [0, 0, 1, 1]
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = "\n".join(b.get("html") or "" for b in blocks if not b.get("skipped"))
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = [layout.block(layout.label(LABELS, b["label"]), b["bbox"], (w, h),
                                              " ".join(_TAG.sub(" ", b.get("html") or "").split()))
                                 for b in blocks if b.get("label") != "BlankPage"]
        except errors.VendorError as exc:
            errs["blocks"] = f"the adapter couldn't read the answer: VendorError: {exc}"[:300]
    return outputs, errs
