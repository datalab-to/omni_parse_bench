"""PP-StructureV3 (PaddleOCR's PPStructureV3 pipeline), served from providers/serve/pp-structurev3/ on any
host; a GPU is optional.

Licenses: PaddleOCR (3.7.0), PaddleX (3.7.2) and paddlepaddle (3.2.2) are Apache-2.0 on PyPI. Every model the
pipeline loads is Apache-2.0 on its Hugging Face model card (`license: apache-2.0`, read 2026-11-25 for each
of the 13 models in PINNED: PP-DocLayout_plus-L, PP-DocBlockLayout, PP-OCRv5_server_det and _rec,
PP-LCNet_x1_0_doc_ori, _textline_ori and _table_cls, UVDoc, SLANet_plus, SLANeXt_wired, RT-DETR-L wired and
wireless table cell detection, and PP-FormulaNet_plus-L).
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
# Note: the package names its models, so its version decides which; the server's answer says which it ran.
PACKAGE = "paddleocr==3.7.0 (paddlex 3.7.2, paddlepaddle 3.2.2)"
# The Hugging Face models the pipeline loads at its defaults, at the commits its image holds: PaddleX's
# Hugging Face source takes the latest of a model, so the image downloads these (serve/pp-structurev3/
# model_pins.py, which a test keeps equal to this) before PaddleX looks. Their licenses are in the docstring.
PINNED = {
    "PP-DocLayout_plus-L": "aa52b8528c84f9b1a34ac3a88fe0e576edb9d11d",
    "PP-DocBlockLayout": "f270657da59d956ab69ffc2c4722fe1f557bf17b",
    "PP-OCRv5_server_det": "ca867c897ecbca8873081573a802ad70d499cb94",
    "PP-OCRv5_server_rec": "b26c3587fda8da3c8ec0ce357214b4d661ff1558",
    "PP-LCNet_x1_0_doc_ori": "d3b95a6dff5fe8a94f2748e12b61cb26818a0df8",
    "PP-LCNet_x1_0_textline_ori": "cd237a44b0e359d4fe38310a416203cf7403faa5",
    "PP-LCNet_x1_0_table_cls": "2fa6323e7dab88fa883081db1460995f46af2922",
    "UVDoc": "16c3f0ea9c2f0c6a57e24160f7eeaa7574613fa3",
    "SLANet_plus": "bae6e5f8c3c4e7da0c0b7639fdf3228fe76184e2",
    "SLANeXt_wired": "763069fcda6a065f2171753205a32bf899a88d15",
    "RT-DETR-L_wired_table_cell_det": "e2bd53c06b3a815d86acbf5c6779dada58819cfe",
    "RT-DETR-L_wireless_table_cell_det": "25ca86356a601c877476bb0dcc5fd09153d9d64d",
    "PP-FormulaNet_plus-L": "0809597a77f735bfb35354edb632f2e6dff606f3",
}
WEIGHTS = ", ".join(f"PaddlePaddle/{name}@{sha}" for name, sha in PINNED.items())
# PP-DocLayout_plus-L's label_list (its inference.yml) onto views.LABELS, as PaddleOCR-VL's PP-DocLayoutV3
# labels map: the same names mean the same kinds. Every label the layout model has is here; the pipeline gives
# no other.
LABELS = {
    "text": "text", "abstract": "text", "content": "text", "reference": "text", "reference_content": "text",
    "aside_text": "text",
    "paragraph_title": "heading", "doc_title": "heading",
    "footnote": "footnote", "figure_title": "caption", "algorithm": "code",
    "formula": "equation", "formula_number": "equation",
    "header": "page_furniture", "footer": "page_furniture", "number": "page_furniture",
    "table": "table",
    "image": "figure", "chart": "figure", "seal": "figure",
}
_TAG = re.compile(r"<[^>]+>")


@dataclasses.dataclass(frozen=True)
class PpStructureV3(Served):
    """Where the PP-StructureV3 server (serve/pp-structurev3/) answers, and whether the page's headers and
    footers are kept in its markdown.

    Run as PaddleOCR documents it: `paddleocr.PPStructureV3()` with no options (paddleocr 3.7.0), then
    `predict(file)`, so the pipeline's defaults decide everything else (document orientation classification
    and unwarping on, text-line orientation off, tables and formulas recognized, seals and charts not).
    PP-StructureV3 is a pipeline of several models, not one: its layout model (PP-DocLayout_plus-L) finds the
    page's blocks, and
    OCR, table, and formula models read them. Steps 1 to 4 run on the server (serve/pp-structurev3/server.py);
    step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file; the pipeline reads it as it reads any input path: a PDF
                              by its own reader (PaddleX's PDFReader, 144 DPI), an image file as it is.
      2. Image preprocessing  the pipeline's: the page turned upright by its document orientation classifier
                              and straightened by its unwarping model (UVDoc).
      3. Model inference      layout detection, region detection, OCR (PP-OCRv5), table structure and formula
                              recognition, on the CPU unless the server's DEVICE says otherwise.
      4. Vendor output parsing  the pipeline's result: its blocks in reading order (`parsing_res_list`: label,
                              box in the pixels of the upright page, content) and its markdown, with no label
                              left out of it (`markdown_ignore_labels` empty).
      5. Mapping to opb outputs  html is that markdown through `markdown.to_html`; blocks are each block's
                              label (LABELS) and box divided by the upright page's size, then turned back
                              onto the page as sent (`layout.unturned`); text is the content, tags removed.

    Differences from the vendor:

      - every block is kept in the markdown: `markdown_ignore_labels=[]`. The option is documented (PaddleOCR
        docs, version3.x/pipeline_usage/PP-StructureV3.en.md: "Layout tags that need to be ignored in
        Markdown. If set to None, the default value is ['number','footnote','header','header_image','footer',
        'footer_image','aside_text']"); the benchmark scores the whole page for every system, as for
        PaddleOCR-VL; and
      - the models are pinned to commits (PINNED): PaddleX's Hugging Face source downloads the latest of a
        model and has no revision option, so the image puts these commits in PaddleX's model folder first.
        The Hugging Face source is PaddleX 3.7.2's default (`PADDLE_PDX_MODEL_SOURCE` is "huggingface" unless
        set, in paddlex/utils/flags.py; the PaddleOCR docs do not name it).

        docker build -t opb-pp-structurev3 omni_parse_bench/harness/providers/serve/pp-structurev3
        docker run -p 8001:8001 opb-pp-structurev3
        opb init pp-structurev3 > config.yaml
        opb run --config config.yaml --set system.pp-structurev3.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": "paddleocr==3.7.0"},
        metadata={"help": "what its server serves: its models at their commits, and the package"})
    furniture: bool = dataclasses.field(default=True, metadata={
        "help": "keep page numbers, headers, footers, footnotes and side text in the markdown (the "
                "pipeline's default leaves them out)"})

    name: ClassVar[str] = "pp-structurev3"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "pp-structurev3"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: PpStructureV3) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"package": PACKAGE, "pipeline": "PPStructureV3() (documented defaults)",
            "layout": "PP-DocLayout_plus-L", "settings": http.settings(config),
            "page": "the file, loaded by its pipeline"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: PpStructureV3) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def blocks(raw: dict) -> list[dict]:
    """The pipeline's blocks, on the page as sent."""
    frame = (raw["width"], raw["height"])
    # Note: "angle" is how far the pipeline rotated the image counterclockwise to make it upright (cv2's
    # rotation), so the page is that far turned the other way, which is `unturned`'s `turned`.
    angle = raw.get("angle")
    turned = -angle % 360 if angle and angle > 0 else 0
    out = []
    for b in raw.get("parsing_res_list") or []:
        text = " ".join(_TAG.sub(" ", b.get("block_content") or "").split())
        block = layout.block(layout.label(LABELS, b.get("block_label") or ""), b["block_bbox"], frame, text)
        out.append(block | {"bbox": layout.unturned(block["bbox"], turned)})
    return out


def parse(raw: dict, request: contract.Request, config: PpStructureV3 | None = None) -> tuple[dict, dict]:
    if "markdown" not in raw:
        raise errors.SystemFailed(f"no markdown in the answer: {str(raw)[:300]}", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the pipeline's blocks"):
                outputs["blocks"] = blocks(raw)
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
