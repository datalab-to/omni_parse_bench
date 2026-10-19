"""GLM-OCR (zai-org/GLM-OCR), through its SDK's self-hosted pipeline, served from providers/serve/glm_ocr/.

Run as its SDK documents it (github.com/zai-org/GLM-OCR, "Self-host with vLLM / SGLang" and "SDK Server",
`glmocr[selfhosted,server]` 0.1.5). Steps 1 to 4 run on the server (serve/glm_ocr/server.py); step 5
runs here, with no vendor code.

How a page is processed:

  1. Input loading        opb sends the page file; the server hands it to an SDK server as a file path,
                          and the SDK's own page loader opens it: a PDF at its pdf_dpi, 200 DPI, its
                          long edge at most 3500 px; an image as it is.
  2. Image preprocessing  the SDK's: PP-DocLayoutV3 layout detection on the page, then each region
                          cropped for recognition, at its config.yaml settings.
  3. Model inference      vLLM 0.19.0 as the SDK's README serves it (MTP speculation, 3 tokens); each
                          region recognised by the model at the SDK's sampling (temperature 0, top_k 1,
                          repetition penalty 1.1, 8192 tokens). One SDK server shares one pipeline
                          between concurrent requests, and concurrent requests to one server came back
                          empty, so the server runs 12 SDK servers, each reading one page at a time.
  4. Vendor output parsing  the SDK formats the page: its markdown (`markdown_result`) and its regions
                          (`json_result`: `{label, native_label, content, bbox_2d}`, boxes on a 0-1000
                          grid). A region the SDK failed to read, which it would leave out silently,
                          fails the page instead.
  5. Mapping to opb outputs  html is that markdown, its image placeholders (`![Image 0-0](imgs/...)`,
                          files the server would write) dropped, as for Mistral, through
                          `markdown.to_html`; blocks are the regions, each `native_label` mapped by
                          LABELS.

Differences from the vendor:

  - the SDK's default config abandons the regions it labels header, footer, number, footnote,
    aside_text, reference and header/footer images; the server's `keep` config (its default) reads them,
    since the benchmark scores the whole page, headers and footers included, for every system; its
    answer says which config read it (`sdk_config`); and
  - each page has the benchmark's 900 s.

    docker build -t opb-glm_ocr omni_parse_bench/harness/providers/serve/glm_ocr
    docker run --gpus all -p 8001:8001 opb-glm_ocr
    opb predict --provider glm-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import json
import re
from pathlib import Path

from ... import markdown
from .. import contract, errors, http, layout

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "zai-org/GLM-OCR"
# PP-DocLayoutV3's labels (the SDK's id2label) onto views.LABELS.
LABELS = {
    "text": "text", "abstract": "text", "content": "text", "reference_content": "text",
    "reference": "text",
    "vertical_text": "text", "aside_text": "text", "doc_title": "heading", "paragraph_title": "heading",
    "figure_title": "caption", "footnote": "footnote", "vision_footnote": "footnote",
    "header": "page_furniture", "footer": "page_furniture", "number": "page_furniture",
    "display_formula": "equation", "inline_formula": "equation", "formula_number": "equation",
    "algorithm": "code", "table": "table",
    "image": "figure", "chart": "figure", "seal": "figure", "header_image": "figure",
    "footer_image": "figure",
}
_IMAGE_PLACEHOLDER = re.compile(r"!\[Image \d+-\d+\]\(imgs/[^)]*\)")
_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the GLM-OCR server (serve/glm_ocr/) answers."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "pipeline": "glmocr SDK 0.1.5 self-hosted",
            "page": "the file, loaded by the SDK (a PDF at 200 DPI, at most 3500 px)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    raw = http.parse(config, page, timeout, body=http.page(page))
    return contract.Call(raw, job_id=raw.get("id"))


def _regions(raw: dict) -> list[dict]:
    pages = raw.get("json_result") or []
    if isinstance(pages, str):
        pages = json.loads(pages)
    if pages and isinstance(pages[0], dict):   # one page given as its regions
        pages = [pages]
    return [r for p in pages for r in (p or [])]


def _block(region: dict) -> dict:
    """A region as a block: its SDK label (LABELS), its box on the 0-1000 grid, its text without tags."""
    kind = layout.label(LABELS, region.get("native_label") or region.get("label") or "")
    text = " ".join(_TAG.sub(" ", str(region.get("content") or "")).split())
    return layout.block(kind, region["bbox_2d"], (1000, 1000), text)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The page from `markdown_result`; the blocks from `json_result`. A label LABELS lacks fails the
    blocks only."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        md = _IMAGE_PLACEHOLDER.sub("", raw.get("markdown_result") or "")
        outputs["html"] = markdown.to_html(md)
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = [_block(r) for r in _regions(raw) if r.get("bbox_2d")]
        except errors.VendorError as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
