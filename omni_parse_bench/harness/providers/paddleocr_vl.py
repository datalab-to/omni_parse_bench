"""PaddleOCR-VL-1.6 (PaddlePaddle/PaddleOCR-VL-1.6), served from providers/oss/paddleocr_vl/ on any GPU host.

Run as PaddleOCR's own pipeline runs it (`paddleocr.PaddleOCRVL`, pipeline_version v1.6, paddleocr 3.7.0,
the VLM through its `vllm-server` backend). PaddleOCR-VL is a pipeline, not one model: its layout model
(PP-DocLayoutV3) finds the page's blocks in reading order, and its 0.9B VLM, served by vLLM, reads each
one. Steps 1 to 4 run on the server (oss/paddleocr_vl/server.py); step 5 runs here, with no vendor code.

How a page is processed:

  1. Input loading        opb sends the page file. A PDF goes through the reader the pipeline's batch
                          sampler makes (PaddleX's PDFReader at its render scale 2.0, 144 DPI), and the
                          page it renders to the pipeline; an image file goes to the pipeline as its
                          path, for its own reader (EXIF rotation applied).
  2. Image preprocessing  the pipeline's: layout detection on the page (on the CPU), then each block
                          cropped, within its per-block pixel limits.
  3. Model inference      vLLM 0.31.0 with the recipe's flags for the VLM; the pipeline asks it for each
                          block at its own prompts and sampling.
  4. Vendor output parsing  the pipeline's result: its blocks (`parsing_res_list`: label, box in the
                          pixels of the page as loaded, content) and its markdown, every block kept
                          (`markdown_ignore_labels` empty).
  5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are its blocks,
                          each label from LABELS, content with tags removed. A block type LABELS lacks
                          fails blocks only.

Differences from the vendor:

  - every block is kept in the markdown (Paddle's default list drops headers, footers, footnotes and
    side text; the benchmark scores the whole page for every system);
  - the layout model runs on the CPU (the vendor recommends a GPU, mainly for speed); and
  - each page has the benchmark's 900 s.

    docker build -t opb-paddleocr_vl omni_parse_bench/harness/providers/oss/paddleocr_vl
    docker run --gpus all -p 8001:8001 opb-paddleocr_vl
    opb predict --provider paddleocr-vl --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ... import markdown
from .. import contract, errors, http, layout

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "PaddlePaddle/PaddleOCR-VL-1.6@c5630abae1d940eafe0697512a0325494b02ab42"
# PP-DocLayoutV3's label_list (its inference.yml) onto views.LABELS, as the other vendors' types map.
LABELS = {
    "text": "text", "abstract": "text", "content": "text", "reference": "text",
    "reference_content": "text", "aside_text": "text", "vertical_text": "text",
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
class Config:
    """Where the PaddleOCR-VL server (oss/paddleocr_vl/) answers, and the DPI a PDF is loaded at (the
    pipeline's, PDF_RENDER_SCALE 2.0, by default)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    dpi: int = 144


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "pipeline": "PaddleOCRVL v1.6 (paddleocr 3.7.0)", "layout": "PP-DocLayoutV3",
            "vl_rec_backend": "vllm-server", "markdown_ignore_labels": [],
            "settings": http.settings(config), "page": "the file, loaded by its pipeline"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def blocks(raw: dict) -> list[dict]:
    """The pipeline's blocks, in the image's pixel frame."""
    frame = (raw["width"], raw["height"])
    out = []
    for b in raw.get("parsing_res_list") or []:
        text = " ".join(_TAG.sub(" ", b.get("block_content") or "").split())
        kind = layout.label(LABELS, b.get("block_label") or "")
        out.append(layout.block(kind, b["block_bbox"], frame, text))
    return out


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    if "markdown" not in raw:
        raise errors.VendorError(f"no markdown in the answer: {str(raw)[:300]}", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = blocks(raw)
        except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
