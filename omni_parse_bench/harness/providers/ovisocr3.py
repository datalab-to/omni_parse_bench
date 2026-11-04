"""OvisOCR3 (ATH-MaaS/OvisOCR3), served from providers/serve/ovisocr3/ on any GPU host."""
from __future__ import annotations

import base64
import dataclasses
import json
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import contract, errors, http, layout
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "ATH-MaaS/OvisOCR3@4833d5d2afa6e769ee933f024504d67ace80a24c"
# The card's `prompts/` files: the markdown one gives html, the structured one blocks.
MARKDOWN, STRUCTURED = "document_markdown", "document_structured"
# The categories of document_structured.txt onto views.LABELS: its list is PP-DocLayout's, the same one
# PaddleOCR-VL's layout model draws on, and they map alike. A category not here fails `blocks` only.
LABELS = {
    "text": "text", "abstract": "text", "content": "text", "reference_content": "text",
    "aside_text": "text", "vertical_text": "text",
    "paragraph_title": "heading", "doc_title": "heading",
    "footnote": "footnote", "vision_footnote": "footnote", "figure_title": "caption",
    "algorithm": "code", "display_formula": "equation", "inline_formula": "equation",
    "formula_number": "equation",
    "header": "page_furniture", "footer": "page_furniture", "number": "page_furniture",
    "table": "table",
    "image": "figure", "chart": "figure", "seal": "figure", "header_image": "figure",
    "footer_image": "figure",
}
_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class OvisOcr3(Served):
    """Where the OvisOCR3 server (serve/ovisocr3/) answers, and the model card's settings.

    Run as its model card runs it (huggingface.co/ATH-MaaS/OvisOCR3, "Inference" and "Document Parsing").
    Steps 3 and 4 run on the server (serve/ovisocr3/server.py); steps 1 and 5 run here.

    How a page is processed:

      1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the card takes images
                              only, so the page is rendered as for every model without a renderer of its
                              own.
      2. Image preprocessing  the model's own image processor, in vLLM, with the card's `min_pixels` 448*448
                              and `max_pixels` 2880*2880.
      3. Model inference      vLLM 0.22.1 with `gdn_prefill_backend=triton`, as the card runs it, the
                              weights at the revision pinned in serve/ovisocr3/start.sh; the page image,
                              then a task prompt from the weights' `prompts/`, thinking off, temperature 0,
                              at most 16384 tokens. Two calls per page: `document_markdown` for html and
                              `document_structured` for blocks; each asked once. The card's offline `LLM`
                              is asked here through vLLM's OpenAI-compatible server, with the weights' own
                              sampling defaults off (`--generation-config vllm`).
      4. Vendor output parsing  for `document_markdown`, the card's: the reply stripped, blocks that are
                              only a visual region's `<img src="images/bbox_...">` tag dropped
                              (`filter_imgtags`, on by default as in the card), then its
                              `_clean_truncated_repeats`. The structured reply is left as it is, as the
                              card leaves it.
      5. Mapping to opb outputs  html is the markdown reply through `markdown.to_html`. blocks are the
                              structured reply's JSON array of `{bbox, category, content}`, boxes on a
                              0-1000 grid, each label from LABELS, the text with its tags removed.

    Differences from the vendor:

      - on Blackwell the vision encoder's attention is torch SDPA (start.sh; `MM_ENCODER_ATTN_BACKEND`
        overrides), because vLLM 0.22.1's own choice for it, compiled at start-up, fails there; on other GPUs
        it is vLLM's choice, as the card runs it;
      - the model is asked through vLLM's server rather than the card's offline `LLM`, which is the same
        model, prompt and sampling, but another entry point;
      - the page image is opb's PNG, not the card's own file load; and
      - html and blocks come from two calls, because the card's markdown mode gives no boxes and its
        structured mode is what draws them. The card names no mode for scoring either.

        docker build -t opb-ovisocr3 omni_parse_bench/harness/providers/serve/ovisocr3
        docker run --gpus all -p 8001:8001 opb-ovisocr3
        opb init ovisocr3 > config.yaml
        opb run --config config.yaml --set system.ovisocr3.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "ATH-MaaS/OvisOCR3",
                                 "revision": "4833d5d2afa6e769ee933f024504d67ace80a24c"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    max_tokens: int = 16384
    min_pixels: int = 448 * 448
    max_pixels: int = 2880 * 2880
    filter_imgtags: bool = dataclasses.field(default=True, metadata={
        "help": "drop blocks that are only a visual region's image tag from the markdown reply, as the "
                "card's post-processing does"})
    long_edge: int = dataclasses.field(default=llm.LONG_EDGE, metadata={"local": True})

    name: ClassVar[str] = "ovisocr3"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "ovisocr3"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: OvisOcr3) -> list[contract.Request]:
    """One call for html (the markdown prompt) and one for blocks (the structured prompt)."""
    out = []
    for output, task in (("html", MARKDOWN), ("blocks", STRUCTURED)):
        if output in wants:
            sent = {"weights": WEIGHTS, "task": task, "settings": http.settings(config), "page": "llm png"}
            out.append(contract.Request(frozenset({output}), sent))
    return out


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: OvisOcr3) -> contract.Call:
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "task": request.sent["task"], "settings": http.settings(config)}
    return contract.Call(http.parse(config, page, timeout, body=body))


def items(said: str, cut: bool = False) -> list[dict]:
    """The structured reply's JSON array of {bbox, category, content}. A reply that is no array of objects
    is a malformed answer (`ValueError`), except one the model's token limit cut short (`cut`), which keeps
    every complete item before the cut: that is the model's own limit, where anything else is a defect of the
    reply."""
    said = said.strip()
    try:
        got = json.loads(said)
    except ValueError:
        if not cut: raise
        out, dec, i = [], json.JSONDecoder(), said.find("{")
        while 0 <= i < len(said):
            try:
                obj, end = dec.raw_decode(said, i)
            except ValueError:
                break
            if isinstance(obj, dict): out.append(obj)
            i = said.find("{", end)
        return out
    if not (isinstance(got, list) and all(isinstance(x, dict) for x in got)):
        raise ValueError("the structured reply is not a JSON array of objects")
    return got


def blocks(said: str, cut: bool = False) -> list[dict]:
    out = []
    for x in items(said, cut):
        box = x.get("bbox")
        if not (isinstance(box, list) and len(box) == 4 and all(isinstance(v, (int, float)) for v in box)):
            continue
        kind = str(x.get("category") or "").strip().lower()
        out.append(layout.block(layout.label(LABELS, kind), [float(v) for v in box], (1000, 1000),
                                " ".join(_TAG.sub(" ", str(x.get("content") or "")).split())))
    return out


def parse(raw: dict, request: contract.Request, config: OvisOcr3 | None = None) -> tuple[dict, dict]:
    """The markdown reply as the page, the structured reply as blocks."""
    text = raw["text"] or ""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(text)
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the reply's items"):
                outputs["blocks"] = blocks(text, raw.get("finish_reason") == "length")
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
