"""Infinity-Parser2 (infly/Infinity-Parser2-Pro, -Flash), served from providers/serve/infinity-parser2/ on a
GPU host.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
# The doc2json prompt's categories onto views.LABELS.
LABELS = {
    "text": "text", "title": "heading", "header": "page_furniture", "footer": "page_furniture",
    "figure": "figure", "table": "table", "formula": "equation", "figure_caption": "caption",
    "table_caption": "caption", "formula_caption": "caption", "figure_footnote": "footnote",
    "table_footnote": "footnote", "page_footnote": "footnote",
    # Note: not in the prompt's list, but the models emit them. `label` held form field labels ("8.
    # Interest Rate"), `table_text` held table captions, and a signature is a figure, as for Reducto.
    "form": "form", "label": "form", "table_text": "caption", "signature": "figure",
}



@dataclasses.dataclass(frozen=True)
class Infinity(Served):
    """Where the Infinity-Parser2 server (serve/infinity-parser2/) answers, the model it serves, and its
    sampling (the SDK's by default).

    Run as the vendor's `infinity_parser2` SDK (0.4.0, github.com/infly-ai/INF-MLLM) runs it through its
    vLLM backends. Steps 1 to 4 run on the server (serve/infinity-parser2/server.py); step 5 runs here, with
    no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the SDK's
                              `convert_pdf_to_images` at 300 DPI (its default, and its own benchmark's);
                              an image file goes as it is.
      2. Image preprocessing  the SDK's `encode_image_to_base64`, 2048 to 16777216 pixels, sent as PNG.
                              Without torch, as in any client-only install, `qwen-vl-utils` doesn't import
                              and the SDK only shrinks a page above the maximum; vLLM's image processor
                              then applies the same smart resize, so the model sees the same grid.
      3. Model inference      vLLM 0.17.1 with the model card's flags (Pro across two GPUs), the image
                              then the SDK's `doc2json` prompt, temperature 0, top_p 1, at most 32768
                              tokens, thinking off; asked once.
      4. Vendor output parsing  the SDK's own reading: the JSON block extracted, a list cut at the token
                              limit truncated at its last complete element, and `convert_json_to_markdown`
                              for the page, headers, footers and page footnotes kept
                              (`keep_header_footer=True`).
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are the
                              elements `{bbox, category, text}`, each label from LABELS, boxes on a 0-1000
                              grid, none when the reply is not a JSON list of elements. The prompt asks for
                              a figure's text to be empty.

    Differences from the vendor:

      - headers, footers and page footnotes are kept (the SDK leaves them out by default; the benchmark
        scores the whole page for every system).

    The server serves Pro or Flash, as its WEIGHTS say, and says which in every reply (`served`), so a run
    records which answered.

        docker build -t opb-infinity-parser2 omni_parse_bench/harness/providers/serve/infinity-parser2
        docker run --gpus all -p 8001:8001 opb-infinity-parser2
        opb init infinity-parser2 > config.yaml
        opb run --config config.yaml --set system.infinity-parser2.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "infly/Infinity-Parser2-Pro",
                                 "revision": "b27d470100514329fc6439aada8f16ccea5f9e2a"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 32768
    dpi: int = 300
    min_pixels: int = 2048
    max_pixels: int = 16777216

    name: ClassVar[str] = "infinity-parser2"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "infinity-parser2"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Infinity) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sent = {"prompt": "doc2json", "sdk": "infinity_parser2==0.4.0",
            "settings": http.settings(config), "keep_header_footer": True,
            "page": "the file, loaded by the SDK"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Infinity) -> contract.Call:
    raw = http.parse(config, page, timeout)
    # Note: a reply cut at the token limit is kept: its complete elements are read, as the SDK reads them.
    with adapter.reading("the server's answer"):
        completion = raw["completion"]
    return contract.Call(raw, cost=llm.tokens([completion]), job_id=completion.get("id"))


def _items(text: str) -> list[dict] | None:
    try:
        items = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(items, list):
        return None
    if items and isinstance(items[0], list):
        items = [el for pg in items for el in pg]
    return [x for x in items if isinstance(x, dict)]


def parse(raw: dict, request: contract.Request, config: Infinity | None = None) -> tuple[dict, dict]:
    """The SDK's reading, headers and footers kept; the elements as blocks."""
    llm.content(raw["completion"])     # the reply finished, or was cut at its token limit
    if "json" not in raw:
        raise errors.SystemFailed("the reply is empty", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        items = _items(raw["json"])
        if items is None:
            errs["blocks"] = "the reply is not a JSON list of elements: no layout"
        else:
            try:
                with adapter.reading("the reply's elements"):
                    outputs["blocks"] = [
                        layout.block(layout.label(LABELS, str(x.get("category"))), x["bbox"], (1000, 1000),
                                     " ".join(views.text(str(x.get("text") or "")).split()))
                        for x in items if isinstance(x.get("bbox"), list) and len(x["bbox"]) == 4]
            except errors.SystemFailed as exc:
                errs["blocks"] = errors.unread(exc)
    return outputs, errs
