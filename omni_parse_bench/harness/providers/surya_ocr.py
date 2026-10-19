"""Surya OCR 2 (datalab-to/surya-ocr-2), served from providers/serve/surya/ on any GPU host.

The adapter is `SuryaOcr`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, ClassVar

from .. import contract, errors, http, layout
from ..adapter import PageAdapter

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
class SuryaOcr(PageAdapter):
    """Where the Surya OCR 2 server (serve/surya/) answers, and the DPI a PDF is loaded at (the
    `surya_ocr` command's, IMAGE_DPI_HIGHRES, by default).

    Run as the public `surya-ocr` package (0.22.1) runs it with its `surya_ocr` command. Steps 1 to 4 run on
    the server (serve/surya/server.py); step 5 runs here, with no vendor code.

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

        docker build -t opb-surya omni_parse_bench/harness/providers/serve/surya
        docker run --gpus all -p 8001:8001 opb-surya
        opb run --providers surya-ocr --sample 20 \\
            --options '{"surya-ocr": {"base_url": "http://localhost:8001"}}'

    OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
    """

    base_url: str = "http://127.0.0.1:8001"
    dpi: int = 192

    name: ClassVar[str] = "surya-ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: SuryaOcr) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "package": PACKAGE, "mode": "RecognitionPredictor(full_page=True)",
            "fullpage_regen": True,
            "settings": http.settings(config), "page": "the file, loaded as its surya_ocr command loads one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: SuryaOcr) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def parse(raw: dict, request: contract.Request, config: SuryaOcr | None = None) -> tuple[dict, dict]:
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
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
