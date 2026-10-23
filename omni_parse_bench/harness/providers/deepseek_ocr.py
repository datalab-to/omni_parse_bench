"""DeepSeek-OCR-2 (deepseek-ai/DeepSeek-OCR-2), served from providers/serve/deepseek-ocr/ on any GPU host."""
from __future__ import annotations

import ast
import dataclasses
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import contract, errors, http, layout
from ..adapter import Served

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "deepseek-ai/DeepSeek-OCR-2"
PROMPT = "<image>\n<|grounding|>Convert the document to markdown."
GRID = 999
REF = re.compile(r"(<\|ref\|>(.*?)<\|/ref\|><\|det\|>(.*?)<\|/det\|>)", re.S)
FORMULA = re.compile(r"\\\[(.*?)\\\]", re.S)
SPECIAL = re.compile(r"<[|｜][^<>]{0,40}[|｜]>")
_TAG = re.compile(r"<[^>]+>")
# DeepSeek-OCR's layout labels (as it emits them) onto views.LABELS.
LABELS = {
    "text": "text", "aside_text": "text", "ref_text": "text", "title": "heading", "sub_title": "heading",
    "list": "list", "image_caption": "caption", "table_caption": "caption", "caption": "caption",
    "figure_title": "caption",
    "footnote": "footnote", "table_footnote": "footnote", "image_footnote": "footnote",
    "page_footnote": "footnote", "header": "page_furniture", "footer": "page_furniture",
    "page_number": "page_furniture", "equation": "equation", "formula_number": "equation", "code": "code",
    "algorithm": "code",
    "table": "table", "image": "figure", "chart": "figure",
}


@dataclasses.dataclass(frozen=True)
class DeepseekOcr(Served):
    """Where the DeepSeek-OCR-2 server (serve/deepseek-ocr/) answers, and its sampling (the repository's
    scripts' by default; top_p, which they leave unset, at vLLM's 1.0).

    Run as its repository runs it (github.com/deepseek-ai/DeepSeek-OCR-2 at 2f3699e, DeepSeek-OCR2-vllm),
    which it does only as batch scripts; the server wraps that engine in one route. Steps 1 to 4 run on the
    server (serve/deepseek-ocr/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered as run_dpsk_ocr2_pdf.py renders
                              one (PyMuPDF at 144 DPI); an image file is opened as run_dpsk_ocr2_image.py
                              opens one, its EXIF rotation applied.
      2. Image preprocessing  the repository's image processor in crop mode: one 1024 px global view plus
                              768 px tiles (2 to 6, by the page's shape).
      3. Model inference      vLLM 0.8.5 with the V0 engine and the repository's own model code registered
                              (the engine arguments of run_dpsk_ocr2_eval_batch.py); the prompt
                              `<image>\\n<|grounding|>Convert the document to markdown.`, temperature 0, at
                              most 8192 tokens, special tokens kept, and its no-repeat n-gram logits
                              processor at ngram_size 40, window_size 90, `<td>` and `</td>` whitelisted
                              (the values of run_dpsk_ocr2_eval_batch.py).
      4. Vendor output parsing  the reply is markdown in blocks, each opened by
                              `<|ref|>label<|/ref|><|det|>[[x1, y1, x2, y2]]<|/det|>`, boxes on a 0-999
                              grid; the page is the repository's evaluation post-processing
                              (run_dpsk_ocr2_eval_batch.py: display formulas cleaned of `\\quad (n)` tags,
                              every marker removed).
      5. Mapping to opb outputs  html is that page through `markdown.to_html`; blocks are the markers, each
                              label from LABELS, with the text up to the next marker.


        docker build -t opb-deepseek-ocr omni_parse_bench/harness/providers/serve/deepseek-ocr
        docker run --gpus all -p 8001:8001 opb-deepseek-ocr
        opb run --system deepseek-ocr --sample 20 \\
            --options '{"base_url": "http://localhost:8001"}'
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "deepseek-ai/DeepSeek-OCR-2",
                                 "revision": "aaa02f3811945a91062062994c5c4a3f4c0af2b0"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 8192
    dpi: int = 144
    ngram_size: int = 40
    window_size: int = 90

    name: ClassVar[str] = "deepseek-ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "deepseek-ocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: DeepseekOcr) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "prompt": PROMPT, "vllm": "0.8.5 (V0 engine)",
            "settings": http.settings(config), "skip_special_tokens": False, "crop_mode": True,
            "ngram_whitelist_token_ids": [128821, 128822], "page": "the file, loaded as its scripts load one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: DeepseekOcr) -> contract.Call:
    raw = http.parse(config, page, timeout)
    return contract.Call(raw, cost=contract.Cost(tokens_out=raw.get("tokens")))


def page_markdown(said: str) -> str:
    """The repository's evaluation post-processing: formulas cleaned, every ref/det marker removed."""
    said = FORMULA.sub(lambda m: r"\[" + re.sub(r"\\quad\s*\([^)]*\)", "", m.group(1)).strip() + r"\]", said)
    for whole, _, _ in REF.findall(said):
        said = said.replace(whole, "").replace("\n\n\n\n", "\n\n").replace("\n\n\n", "\n\n")
    return SPECIAL.sub("", said).strip()


def blocks(said: str) -> list[dict]:
    """Each marker with its box (the first, when it gives several) and the text up to the next one."""
    marks = list(REF.finditer(said))
    out = []
    for i, m in enumerate(marks):
        try:
            boxes = ast.literal_eval(m.group(3).strip())
        except (ValueError, SyntaxError):
            continue
        if boxes and isinstance(boxes[0], (int, float)): boxes = [boxes]
        body = said[m.end(): marks[i + 1].start() if i + 1 < len(marks) else len(said)]
        text = " ".join(_TAG.sub(" ", SPECIAL.sub("", body)).split())
        kind = layout.label(LABELS, m.group(2).strip())
        for box in boxes:
            if len(box) == 4:
                out.append(layout.block(kind, [float(v) for v in box], (GRID, GRID), text))
    return out


def parse(raw: dict, request: contract.Request, config: DeepseekOcr | None = None) -> tuple[dict, dict]:
    """The page and its blocks."""
    # Note: a reply cut at the token limit is read as it is, as the repository's scripts read it.
    if raw.get("finish_reason") not in ("stop", "length"):
        raise errors.SystemFailed(f"the reply didn't finish: {raw.get('finish_reason')}", status=200)
    said = raw.get("raw") or ""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(page_markdown(said))
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the reply's boxes"):
                outputs["blocks"] = blocks(said)
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
