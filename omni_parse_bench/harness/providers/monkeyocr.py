"""MonkeyOCR-pro-3B (echo840/MonkeyOCR-pro-3B), served from providers/serve/monkeyocr/ on any GPU host.

Licenses: the code (github.com/Yuliang-Liu/MonkeyOCR) is Apache-2.0. The weights are not: the README ("License
and Commercial Use") provides the MonkeyOCR v1 model weights "for academic research and non-commercial
evaluation only", and any commercial or production use needs a separate written license from the authors.
The weights' model card says the same ("academic research and non-commercial use only"). The image holds the
code only; the weights download when the server starts.
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
WEIGHTS = "echo840/MonkeyOCR-pro-3B"
REVISION = "913c6e24b2ef293e6384f74a3e374d0c043c9741"
CODE = "Yuliang-Liu/MonkeyOCR@73dee40fef504ed73ba70f5a43038f692bd4b329"
# MonkeyOCR's block types, as its middle JSON gives them (magic_pdf.config.ocr_content_type.BlockType; an
# image or a table block is read as its parts), onto views.LABELS, plus the PP-DocLayoutV2 labels that its
# "abandon" category folds together (header, footer, number, header_image, footer_image, seal,
# formula_number). With `--pred-abandon` those regions are read as plain text blocks, so the server
# restores each one's layout label (serve/monkeyocr/server.py, `abandoned`). Those labels map as glm_ocr and
# paddleocr_vl, which use the same PP-DocLayout vocabulary, map them: header, footer and number to
# page_furniture; the images and seals to figure; formula_number to equation.
#
#   - `index` is MonkeyOCR's table-of-contents block (para_split_v3); it is text lines, so text. A person
#     is asked to sign this off; and
#   - a footnote, a figure title or a reference is a plain `text` block already in the layout model's fold,
#     so it is text here, not footnote or caption.
LABELS = {
    "text": "text", "index": "text",
    "title": "heading",
    "list": "list",
    "interline_equation": "equation",
    "image_body": "figure", "image_caption": "caption", "image_footnote": "footnote",
    "table_body": "table", "table_caption": "caption", "table_footnote": "footnote",
    "header": "page_furniture", "footer": "page_furniture", "number": "page_furniture",
    "header_image": "figure", "footer_image": "figure", "seal": "figure", "formula_number": "equation",
}


@dataclasses.dataclass(frozen=True)
class MonkeyOcr(Served):
    """Where the MonkeyOCR server (serve/monkeyocr/) answers.

    Run as its repository's `parse.py` runs a file (github.com/Yuliang-Liu/MonkeyOCR at 73dee40, the
    end-to-end `python parse.py input_path`: no `-t` single task, no `-g` grouping, no `-s` page split),
    with `--pred-abandon` on (its README, "python parse.py input.pdf --pred-abandon  # Enable predicting
    abandon elements"), with `MonkeyOCR-pro-3B`, the model its README's quick start downloads by default
    (`tools/download_model.py -n MonkeyOCR-pro-3B`; its leaner 1.2B sibling is "approximately a 36% speed
    improvement ... with approximately 1.6% drop in performance"), on the LMDeploy backend (0.9.2), which
    its install guide recommends and its `model_configs.yaml` sets. Steps 1 to 4 run on the server
    (serve/monkeyocr/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is opened by `PymuDocDataset`, an image file
                              by `ImageDataset` (it wraps the image in a one-page PDF); either page is
                              rendered by `fitz_doc_to_image` at 200 DPI (72 DPI instead past 4500 px).
      2. Image preprocessing  the repository's: layout detection by PP-DocLayoutV2 (PaddleX 3.3.0) on the
                              page image, each region cropped from it.
      3. Model inference      `doc_analyze_llm`: the layout's regions in reading order (the `layoutreader`
                              model), then the 3B model reads each region from its crop with the
                              repository's task prompts (text, formula, table), at its defaults, with
                              LMDeploy; asked once.
      4. Vendor output parsing  `pipe_ocr_mode` builds the page's blocks (the middle JSON, `your_middle.json`
                              of its README: block types, boxes and contents); its `get_markdown` writes
                              the page's `.md`: text, `$$` formulas, tables as html, pictures as image
                              links. Headers, footers and page numbers are in both (`--pred-abandon`).
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are the middle
                              JSON's blocks (an image or table block as its body, caption and footnote
                              parts), each type mapped by LABELS, its text with tags removed, its box
                              divided by the page's size.

    `--pred-abandon` is the one non-default setting. Without it MonkeyOCR leaves headers, footers and page
    numbers unread and out of its output, and the benchmark scores page furniture, so with it the page is the
    whole page, as for every other system.

    Differences from the vendor: none.

        docker build -t opb-monkeyocr omni_parse_bench/harness/providers/serve/monkeyocr
        docker run --gpus all -p 8001:8001 opb-monkeyocr
        opb init monkeyocr > config.yaml
        opb run --config config.yaml --set system.monkeyocr.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": REVISION},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})

    name: ClassVar[str] = "monkeyocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "monkeyocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: MonkeyOcr) -> list[contract.Request]:
    """One end-to-end parse answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "code": CODE, "backend": "lmdeploy 0.9.2", "mode": "end-to-end parse",
            "pred_abandon": True,
            "page": "the file, rendered by MonkeyOCR (200 DPI, at most 4500 px)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: MonkeyOcr) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout, body=http.page(page)))


def parse(raw: dict, request: contract.Request, config: MonkeyOcr | None = None) -> tuple[dict, dict]:
    """The page from MonkeyOCR's markdown; the blocks from its middle JSON, with their labels."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        try:
            with adapter.reading("MonkeyOCR's blocks"):
                found, frame = raw["blocks"], tuple(raw["page_size"])
                outputs["blocks"] = [layout.block(layout.label(LABELS, b["type"]), b["bbox"], frame,
                                                  " ".join(views.text(b.get("content") or "").split()))
                                     for b in found]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
