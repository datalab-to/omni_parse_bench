"""MinerU2.5-Pro (opendatalab/MinerU2.5-Pro-2605-1.2B), served from providers/serve/mineru/ on any GPU
host.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import contract, errors, http, layout
from ..adapter import Served

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "opendatalab/MinerU2.5-Pro-2605-1.2B"
CLIENT = "mineru-vl-utils==2.0.7"
# MinerU's block types (mineru_vl_utils.structs.BlockType) onto views.LABELS. `unknown` is a block
# the model couldn't type; it reads as running text, which is also what `layout.guess` gives.
LABELS = {
    "text": "text", "aside_text": "text", "ref_text": "text", "index": "text", "phonetic": "text",
    "unknown": "text",
    "title": "heading", "doc_title": "heading", "paragraph_title": "heading",
    "list": "list", "list_item": "list",
    "caption": "caption", "table_caption": "caption", "image_caption": "caption",
    "code_caption": "caption",
    "footnote": "footnote", "table_footnote": "footnote", "image_footnote": "footnote",
    "page_footnote": "footnote",
    "header": "page_furniture", "footer": "page_furniture", "page_number": "page_furniture",
    "equation": "equation", "equation_block": "equation", "formula_number": "equation",
    "code": "code", "algorithm": "code",
    "table": "table",
    "image": "figure", "chart": "figure", "image_block": "figure",
}
_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class MinerU(Served):
    """Where the MinerU2.5-Pro server (serve/mineru/) answers.

    Run as its model card and client run it (github.com/opendatalab/mineru-vl-utils 2.0.7, `MinerUClient`
    with the `http-client` backend), the page rendered as MinerU renders one. Steps 1 to 4 run on the server
    (serve/mineru/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by MinerU's docvortex package
                              (`load_images_from_pdf_core`, 0.5.16): 200 DPI, its long edge at most 3500 px.
                              An image file is opened as it is (MinerU's own path for an image file is not
                              traced here).
      2. Image preprocessing  the client's: layout detection on a 1036 x 1036 copy of the page, then each
                              block cropped from the page as loaded.
      3. Model inference      vLLM 0.21.0 with MinerU's logits processor (`MinerULogitsProcessor`, for the
                              client's no-repeat n-gram setting); the client's `two_step_extract`, layout
                              first, then each block's content from its crop, at its default prompts and
                              sampling. Image analysis stays off (the model card's default).
      4. Vendor output parsing  the client's blocks `{type, bbox, angle, content}`, boxes from 0 to 1, and
                              its `json2md` over them: truncated paragraphs merged, headers and footers kept,
                              images left out.
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are the list, each
                              type mapped by LABELS.


        docker build -t opb-mineru omni_parse_bench/harness/providers/serve/mineru
        docker run --gpus all -p 8001:8001 opb-mineru
        opb init mineru > config.yaml
        opb run --config config.yaml --set system.mineru.base_url=http://localhost:8001 --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "opendatalab/MinerU2.5-Pro-2605-1.2B",
                                 "revision": "08aaea840498d49ce16247b6263196cf02814885"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})

    name: ClassVar[str] = "mineru"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "mineru"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: MinerU) -> list[contract.Request]:
    """One two-step extraction answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "client": CLIENT, "method": "two_step_extract", "image_analysis": False,
            "logits_processor": "MinerULogitsProcessor",
            "page": "the file, rendered by MinerU's docvortex (200 DPI, at most 3500 px)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: MinerU) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout, body=http.page(page)))


def parse(raw: dict, request: contract.Request, config: MinerU | None = None) -> tuple[dict, dict]:
    """The page from the client's `json2md`; the blocks with their labels."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        found = raw["blocks"]
        try:
            with adapter.reading("the client's blocks"):
                outputs["blocks"] = [layout.block(layout.label(LABELS, b["type"]), b["bbox"], (1, 1),
                                                  " ".join(_TAG.sub(" ", b.get("content") or "").split()))
                                     for b in found]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
