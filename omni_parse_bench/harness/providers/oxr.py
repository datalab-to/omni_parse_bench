"""OXR-1.0 (SoMarkAI/OXR-1.0), through SoMark's own parsing API, served from providers/serve/oxr/ on any GPU
host."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Served

WEIGHTS = "SoMarkAI/OXR-1.0"
REVISION = "c708407f9d2b4df658f2543d9132b62bb7221df4"
API = "SoMarkAI/OXR@c1a1dcb312ee9f691404f127785510453c0d9350"
SUPPORTS = frozenset({"html", "markdown", "blocks"})
# The API's block types (oxr/pipeline/models.py's BlockType, and "Chemical Equation", a formula with \ce).
LABELS = {
    "Text": "text", "Title": "heading", "Caption": "caption", "Footnote": "footnote",
    "Formula": "equation", "Chemical Equation": "equation", "Code Block": "code", "Table": "table",
    "Picture": "figure", "Stamp": "figure", "Chemical Structure": "figure",
    "Page-header": "page_furniture", "Page-footer": "page_furniture",
}


@dataclasses.dataclass(frozen=True)
class Oxr(Served):
    """Where the OXR-1.0 server (serve/oxr/) answers.

    Run as SoMark's all-in-one image runs it (github.com/SoMarkAI/OXR, its API's defaults). Steps 1 to 4 run
    on the server, in SoMark's code; step 5 runs here.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the API (sopdf, 150 DPI); an image
                              is decoded as it is.
      2. Layout               the D-FINE layout model in the model repository (layout_analysis/), on the GPU,
                              its boxes kept at confidence 0.5 and above.
      3. Model inference      vLLM 0.25.1 with the model's plugin. OXR reads each block's crop with its type's
                              prompt and orders the blocks from their boxes; a picture is not read. The API's
                              defaults throughout, but for page furniture, which it drops unless asked
                              (`keep_header_footer`) and opb keeps, as for every system.
      4. Vendor output        the API's Markdown and its JSON page: each block's type, pixel box and content
                              (text, LaTeX, a table's HTML), in reading order.
      5. Output               `markdown` as given; `html` that Markdown as HTML; `blocks` the JSON's blocks,
                              their types by LABELS and boxes as fractions of the page.

        opb init oxr > oxr.yaml
        opb run --config oxr.yaml --set system.oxr.base_url=http://HOST:8001
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": REVISION},
        metadata={"help": "the weights and revision, checked against the server"})

    name: ClassVar[str] = "oxr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "oxr"
    # Note: the API sends layout 8 pages at a time and holds 16 model requests in flight, as vLLM's
    # --max-num-seqs.
    workers: ClassVar[int] = 8

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return contract.Call(http.parse(self, page, timeout))

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request)


def requests(wants: frozenset[str]) -> list[contract.Request]:
    if not (outputs := wants & SUPPORTS): return []
    sent = {"api": API, "output_formats": ["markdown", "json"],
            "feature_config": {"keep_header_footer": True},
            "page": "the file, loaded by the API (PDF: sopdf at 150 DPI)"}
    return [contract.Request(outputs, sent)]


def parse(raw: dict, request: contract.Request) -> tuple[dict, dict]:
    outputs, errs = {}, {}
    with adapter.reading("OXR's parse result"):
        text = raw["outputs"]["markdown"]
        if not isinstance(text, str):
            raise errors.SystemFailed("OXR's markdown must be a string", status=200)
        if "markdown" in request.outputs: outputs["markdown"] = text
        if "html" in request.outputs: outputs["html"] = markdown.to_html(text)
    if "blocks" in request.outputs:
        try:
            with adapter.reading("OXR's layout blocks"):
                pages = raw["outputs"]["json"]["pages"]
                if len(pages) != 1:
                    raise errors.SystemFailed(f"OXR gave {len(pages)} pages for one page", status=200)
                frame = (pages[0]["page_size"]["w"], pages[0]["page_size"]["h"])
                if not all(n > 0 for n in frame):
                    raise errors.SystemFailed("OXR's page dimensions must be positive", status=200)
                outputs["blocks"] = [
                    layout.block(layout.label(LABELS, b["type"]), b["bbox"], frame,
                                 views.text(markdown.to_html(b["content"])))
                    for b in pages[0]["blocks"]]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
