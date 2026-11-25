"""Dolphin-v2 (ByteDance/Dolphin-v2, 3B), served from providers/serve/dolphin-v2/ on any GPU host.

Licenses: the repository (github.com/bytedance/Dolphin) and the weights (huggingface.co/ByteDance/Dolphin-v2)
both carry the Qwen RESEARCH LICENSE AGREEMENT as their LICENSE file, which grants use "FOR NON-COMMERCIAL
PURPOSES ONLY" ("Non-Commercial" meaning "for research or evaluation purposes only"); the model builds on
Qwen2.5-VL-3B. The README's license badge and the code files' SPDX headers say MIT, which the LICENSE file
contradicts; both are treated as non-commercial here. The image holds the code only; the weights download when
the server starts.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Served

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "ByteDance/Dolphin-v2"
REVISION = "c37c62768c644bb594da4283149c627765aa80f3"
CODE = "bytedance/Dolphin@befa5dad986f86396b73cbd8c37e557b5770c902"
# Dolphin-v2's 21 element types (the model card's "Supported Element Types") onto views.LABELS.
#
#   - `catalogue` (a table of contents) is lines of text, so text; and `reference` (bibliography entries)
#     and `half_para` (a paragraph spanning columns or pages) are text. `catalogue` is the one a person is
#     asked to sign off.
#   - `watermark` is page_furniture, as hunyuan.py maps its `watermark`. `anno` (annotations) is in
#     UNMAPPED: no existing adapter maps an equivalent class (none has one) and nothing in views.LABELS is
#     clearly the same kind, so no block is returned for it (its text stays in the page's html and markdown).
#   - `distorted_page` (the whole page as one element, when the page is judged photographed or its layout
#     boxes overlap) is no layout: the page's blocks fail, with its html still read.
LABELS = {
    "sec_0": "heading", "sec_1": "heading", "sec_2": "heading", "sec_3": "heading", "sec_4": "heading",
    "sec_5": "heading",
    "para": "text", "half_para": "text", "catalogue": "text", "reference": "text",
    "list": "list",
    "cap": "caption",
    "fnote": "footnote",
    "header": "page_furniture", "foot": "page_furniture", "watermark": "page_furniture",
    "equ": "equation",
    "code": "code",
    "tab": "table",
    "fig": "figure",
}
UNMAPPED = frozenset({"anno"})
WHOLE_PAGE = "distorted_page"


@dataclasses.dataclass(frozen=True)
class DolphinV2(Served):
    """Where the Dolphin-v2 server (serve/dolphin-v2/) answers.

    Run as its README runs a page, `python demo_page.py --model_path ./hf_model --input_path <page>`
    ("Page-level Parsing", github.com/bytedance/Dolphin at befa5dad), on Hugging Face transformers (4.51.0,
    bfloat16), its documented framework; `--max_batch_size` is its default 4 and `--post_process` is off,
    its default. Steps 1 to 4 run on the server (serve/dolphin-v2/server.py); step 5 runs here, with no
    vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the repository's
                              `convert_pdf_to_images` (the page's long edge 896 px); an image file is opened
                              as RGB.
      2. Image preprocessing  the model's own: `resize_img` (long edge at most 1600 px) and Qwen2.5-VL's
                              `smart_resize` (factor 28, at most 2,560,000 pixels).
      3. Model inference      stage 1, "Parse the reading order of this document.", once on the page: its
                              elements in reading order, each `[x0,y0,x1,y1][label][tags]` in pixels; stage
                              2, each element cropped from the page and read in batches by type (tables
                              "Parse the table in the image.", formulas "Read formula in the image.", code
                              "Read code in the image.", the rest "Read text in the image."), greedy, at
                              most 4096 new tokens. Figures are cropped and not read. A reply that isn't a
                              layout, or whose boxes overlap too much (a photographed page), is parsed as
                              one whole-page element (`distorted_page`).
      4. Vendor output parsing  the repository's `process_elements` results `{label, bbox, text,
                              reading_order, tags}`, boxes in the page's pixels, and its `MarkdownConverter`
                              markdown: headings as `#`, formulas as `$$`, tables as their html, code in a
                              fence, lists as `- `, figures as image links.
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are the elements,
                              each label from LABELS (a figure has no text), boxes divided by the page's
                              size.

    Differences from the vendor: none.

        docker build -t opb-dolphin-v2 omni_parse_bench/harness/providers/serve/dolphin-v2
        docker run --gpus all -p 8001:8001 opb-dolphin-v2
        opb init dolphin-v2 > config.yaml
        opb run --config config.yaml --set system.dolphin-v2.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": REVISION},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})

    name: ClassVar[str] = "dolphin-v2"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "dolphin-v2"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: DolphinV2) -> list[contract.Request]:
    """One two-stage page parse answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "code": CODE, "framework": "transformers 4.51.0, bfloat16",
            "mode": "page-level parsing", "max_batch_size": 4, "post_process": False,
            "page": "the file (a PDF rendered with its long edge at 896 px)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: DolphinV2) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout, body=http.page(page)))


def parse(raw: dict, request: contract.Request, config: DolphinV2 | None = None) -> tuple[dict, dict]:
    """The page from the repository's markdown; the blocks from its elements, with their labels."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        try:
            with adapter.reading("Dolphin-v2's elements"):
                found, frame = raw["elements"], tuple(raw["image_size"])
                if any(e["label"] == WHOLE_PAGE for e in found):
                    errs["blocks"] = "the page was parsed whole (distorted_page): no layout"
                else:
                    outputs["blocks"] = [
                        layout.block(layout.label(LABELS, e["label"]), e["bbox"], frame,
                                     "" if e["label"] == "fig" else " ".join(views.text(e["text"]).split()))
                        for e in found if e["label"] not in UNMAPPED]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
