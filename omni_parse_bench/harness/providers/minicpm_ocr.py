"""MiniCPM-OCR 1.0, through its official document parsing SDK and PP-DocLayoutV3."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Served

WEIGHTS = "openbmb/MiniCPM-OCR-1.0"
REVISION = "a59a4acf215e34c6d73149e9eafdb88ed2086e39"
SDK_REVISION = "d9de88090765c2895c5ca192699da099f79e3fed"
SUPPORTS = frozenset({"html", "markdown", "blocks"})
# The SDK's PX_LABELS (constants.py), explicitly mapped to the benchmark's labels.
LABELS = {
    "abstract": "text", "content": "text", "reference": "text", "reference_content": "text",
    "text": "text", "vertical_text": "text", "aside_text": "text",
    "algorithm": "code", "doc_title": "heading", "paragraph_title": "heading",
    "figure_title": "caption", "footnote": "footnote", "vision_footnote": "footnote",
    "display_formula": "equation", "inline_formula": "equation", "formula_number": "equation",
    "header": "page_furniture", "footer": "page_furniture", "number": "page_furniture",
    "table": "table", "chart": "figure", "seal": "figure", "image": "figure",
    "header_image": "figure", "footer_image": "figure",
}


@dataclasses.dataclass(frozen=True)
class MiniCpmOcr(Served):
    """MiniCPM-OCR's document pipeline, served from serve/minicpm-ocr/ on a Linux NVIDIA host.

    The SDK, not a full-page prompt, loads a PDF with PyMuPDF at 144 DPI, or opens an image; detects
    layout and reading order with PP-DocLayoutV3; crops regions; recognizes them with their own task
    prompts; and assembles the result. Its OTSL-to-HTML, formula repair and repetition handling are
    vendor postprocessing. The server returns those results and each block's raw recognition text.
    This adapter converts Markdown to HTML and maps typed pixel boxes to fractions of the page.

    Differences from the quickstart: layout runs on CPU; Markdown keeps all labels (the vendor drops
    headers, footers, numbers, footnotes and aside text); DSpark and test-time selection stay off.
    Four pages are in flight by default, one per persistent server pipeline, with `region_workers`
    concurrent region requests inside each page.

        opb init minicpm-ocr > minicpm.yaml
        opb run --config minicpm.yaml --set system.minicpm-ocr.base_url=http://HOST:8001
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": REVISION},
        metadata={"help": "the recognition weights and revision, checked against the server"})
    region_workers: int = dataclasses.field(
        default=32, metadata={"help": "concurrent region recognition requests within each page"})

    name: ClassVar[str] = "minicpm-ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "minicpm-ocr"
    workers: ClassVar[int] = 4

    def __post_init__(self):
        if (isinstance(self.region_workers, bool) or not isinstance(self.region_workers, int)
                or self.region_workers < 1):
            raise ValueError(f"region_workers must be a positive integer, got {self.region_workers!r}")

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request)


def requests(wants: frozenset[str], config: MiniCpmOcr) -> list[contract.Request]:
    if not (outputs := wants & SUPPORTS): return []
    sent = {"sdk": f"OpenBMB/MiniCPM-OCR@{SDK_REVISION}", "layout": "PP-DocLayoutV3 (CPU)",
            "markdown_ignore_labels": [], "dspark": False, "tts": False,
            "page": "the file, loaded by the SDK (PDF: PyMuPDF at 144 DPI)",
            "settings": http.settings(config)}
    return [contract.Request(outputs, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: MiniCpmOcr) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def parse(raw: dict, request: contract.Request) -> tuple[dict, dict]:
    outputs, errs = {}, {}
    with adapter.reading("MiniCPM-OCR's document result"):
        if raw.get("error"):
            raise errors.SystemFailed(f"MiniCPM-OCR: {raw['error']}", status=200)
        if {"html", "markdown"} & request.outputs:
            text = raw["markdown"]
            if not isinstance(text, str):
                raise errors.SystemFailed("MiniCPM-OCR's markdown must be a string", status=200)
            if "markdown" in request.outputs: outputs["markdown"] = text
            if "html" in request.outputs: outputs["html"] = markdown.to_html(raw["html_markdown"])
    if "blocks" in request.outputs:
        try:
            with adapter.reading("MiniCPM-OCR's layout blocks"):
                frame = (raw["image_width"], raw["image_height"])
                if not all(n > 0 for n in frame):
                    raise errors.SystemFailed("MiniCPM-OCR's page dimensions must be positive", status=200)
                outputs["blocks"] = [
                    layout.block(layout.label(LABELS, b["label"]), b["bbox"], frame,
                                 views.text(markdown.to_html(b["content"])))
                    for b in sorted(raw["crop_blocks"], key=lambda b: b["order"])]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
