"""dots.mocr (rednote-hilab/dots.mocr), served from providers/serve/dots/ on any GPU host.

The adapter is `Dots`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import PageAdapter
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
MODEL = "rednote-hilab/dots.mocr"
# dots.mocr's categories (the prompt's list) onto views.LABELS.
LABELS = {
    "Text": "text", "Title": "heading", "Section-header": "heading", "List-item": "list",
    "Caption": "caption", "Footnote": "footnote", "Page-header": "page_furniture",
    "Page-footer": "page_furniture", "Formula": "equation", "Table": "table", "Picture": "figure",
}


@dataclasses.dataclass(frozen=True)
class Dots(PageAdapter):
    """Where the dots.mocr server (serve/dots/) answers, and its sampling (the parser's by default).

    Run as its repository's parser, `DotsMOCRParser`, runs it (github.com/rednote-hilab/dots.mocr at
    23f3e56). Steps 1 to 4 run on the server (serve/dots/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the parser's
                              `load_images_from_pdf` at 200 DPI (its default; a page past 4500 px renders
                              at 72 DPI); an image file goes through its `fetch_image`.
      2. Image preprocessing  `fetch_image` again (smart_resize, factor 28, within its pixel limits).
      3. Model inference      vLLM 0.17.1 with the repository's flags, the `prompt_layout_all_en` prompt
                              behind its image placeholder text (without it vLLM puts a newline before the
                              prompt), temperature 0.1, top_p 1.0, at most 32768 tokens, no system prompt;
                              asked once.
      4. Vendor output parsing  `post_process_output` reads the reply, a JSON list of cells
                              `{bbox, category, text}`, its boxes mapped back to the page as loaded; then
                              `layoutjson2md`'s rules write the page: formulas as display math, tables as
                              their HTML, text as markdown, pictures left out (the parser leaves their text
                              out). A reply whose JSON doesn't parse (one cut at the token limit, say) falls
                              back, as the parser does, to its `OutputCleaner` text.
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are the cells,
                              each label from LABELS, its text with tags removed, boxes divided by the
                              page's size; none when the reply's JSON didn't parse.

    Differences from the vendor:

      - headers and footers are kept, as the parser's `.md` keeps them; and
      - each page has the benchmark's 900 s.

        docker build -t opb-dots omni_parse_bench/harness/providers/serve/dots
        docker run --gpus all -p 8001:8001 opb-dots
        opb run --system dots-mocr --sample 20 \\
            --options '{"base_url": "http://localhost:8001"}'

    OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
    """

    base_url: str = "http://127.0.0.1:8001"
    temperature: float = 0.1
    top_p: float = 1.0
    max_tokens: int = 32768
    dpi: int = 200

    name: ClassVar[str] = "dots-mocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "dots"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Dots) -> list[contract.Request]:
    """One call answers every output."""
    return [contract.Request(wants, {"model": MODEL, "settings": http.settings(config),
                                     "page": "the file, loaded by its parser"})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Dots) -> contract.Call:
    raw = http.parse(config, page, timeout)
    with adapter.reading("the server's answer"):
        completion = raw["completion"]
    return contract.Call(raw, cost=llm.tokens([completion]), job_id=completion.get("id"))


def parse(raw: dict, request: contract.Request, config: Dots | None = None) -> tuple[dict, dict]:
    """The server's page as html, its cells as blocks."""
    if not (raw.get("markdown") or "").strip():
        raise errors.VendorError("the reply is empty", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        if raw["cells"] is None:
            errs["blocks"] = "the reply's JSON doesn't parse: the parser's cleaned text, no layout"
        else:
            try:
                outputs["blocks"] = [
                    layout.block(layout.label(LABELS, c["category"]), c["bbox"], tuple(raw["image_size"]),
                                 " ".join(views.text(str(c.get("text") or "")).split()))
                    for c in raw["cells"] if c.get("bbox")]
            except errors.VendorError as exc:
                errs["blocks"] = errors.unread(exc)
    return outputs, errs
