"""Unlimited-OCR (baidu/Unlimited-OCR), served from providers/serve/unlimited-ocr/ on any GPU host."""
from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Parser
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
MODEL = "baidu/Unlimited-OCR"
PROMPT = "<image>document parsing."
GRID = 999
DET = re.compile(r"<\|det\|>([^<\s]+)(?:\s*\[[^\]]*\])?\s*<\|/det\|>(.*)", re.DOTALL)
DET_BOX = re.compile(r"<\|det\|>([^<\s]+)\s*\[\s*\[?\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*(-?\d+)")
SPECIAL = re.compile(r"<[|｜][^<>]{0,40}[|｜]>")
# The labels the model emits (DeepSeek-OCR's layout set and those seen in its answers) onto
# views.LABELS.
LABELS = {
    "text": "text", "aside_text": "text", "ref_text": "text", "title": "heading", "sub_title": "heading",
    "list": "list", "image_caption": "caption", "table_caption": "caption", "caption": "caption",
    "footnote": "footnote", "table_footnote": "footnote", "image_footnote": "footnote",
    "page_footnote": "footnote", "header": "page_furniture", "footer": "page_furniture",
    "page_number": "page_furniture", "equation": "equation", "code": "code", "algorithm": "code",
    "table": "table", "image": "figure", "chart": "figure",
}


@dataclasses.dataclass(frozen=True)
class UnlimitedOcr(Parser):
    """Where the Unlimited-OCR server (serve/unlimited-ocr/) answers, and its sampling (the recipe's by
    default; top_p, which it leaves unset, at vLLM's 1.0).

    Run as its vLLM recipe runs it (recipes.vllm.ai/baidu/Unlimited-OCR), the page loaded as its own pipeline
    loads one (github.com/baidu/Unlimited-OCR at 92ad94b, infer.py). Steps 1, 3 and 4 run on the server
    (serve/unlimited-ocr/server.py); steps 2 and 5 run in vLLM and here.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the pipeline's `pdf_to_images`
                              at 300 DPI (PyMuPDF); an image file goes as it is; either way through its
                              `encode_image`.
      2. Image preprocessing  the model's own, in vLLM: a single image is read in its gundam crop mode.
      3. Model inference      the recipe's vLLM build and flags (its n-gram logits processor, no prefix
                              cache); the prompt `<image>document parsing.` BEFORE the image (the model has
                              no chat template), temperature 0, special tokens kept, the n-gram processor at
                              ngram_size 35 and window_size 128 (the values for one page), at most 28000
                              tokens; asked once.
      4. Vendor output parsing  none on the server: the reply is markdown in blocks, each opened by
                              `<|det|>label [x0, y0, x1, y1]<|/det|>`, boxes on a 0-999 grid.
      5. Mapping to opb outputs  html is the model card's post-processing (`strip`: markers removed, image
                              blocks dropped, blocks apart) through `markdown.to_html`; blocks are each
                              marker's label (LABELS) and box divided by 999, with its text up to the next
                              marker.

    Differences from the vendor:

      - 28000 output tokens, not the recipe example's 8192: the model card's own `infer` allows 32768 of
        context, and this is that less room for the prompt.

        docker build -t opb-unlimited-ocr omni_parse_bench/harness/providers/serve/unlimited-ocr
        docker run --gpus all -p 8001:8001 opb-unlimited-ocr
        opb run --system unlimited-ocr --sample 20 \\
            --options '{"base_url": "http://localhost:8001"}'
    """

    base_url: str = "http://127.0.0.1:8001"
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 28000
    dpi: int = 300
    ngram_size: int = 35
    window_size: int = 128

    name: ClassVar[str] = "unlimited-ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "unlimited-ocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: UnlimitedOcr) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sha = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
    sent = {"model": MODEL, "prompt": PROMPT, "prompt_sha": sha, "settings": http.settings(config),
            "page": "the file, loaded as its pipeline loads one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: UnlimitedOcr) -> contract.Call:
    raw = http.parse(config, page, timeout)
    with adapter.reading("the server's answer"):
        completion = raw["completion"]
    return contract.Call(raw, cost=llm.tokens([completion]), job_id=completion.get("id"))


def strip(said: str) -> str:
    """The model card's post-processing: det markers removed, image blocks dropped, blocks apart."""
    blocks, cur = [], None
    for line in said.splitlines():
        line = line.rstrip()
        if not line: continue
        if m := DET.match(line):
            if m[1].strip() == "image": continue
            if cur is not None: blocks.append(cur)
            cur = [m[2].strip()] if m[2].strip() else []
            continue
        if cur is None: cur = []
        cur.append(line)
    if cur is not None: blocks.append(cur)
    return SPECIAL.sub("", "\n\n".join("\n".join(b) for b in blocks)).strip()


def blocks(said: str) -> list[dict]:
    """Each det marker with its box, and the text up to the next marker."""
    out, cur = [], None
    for line in said.splitlines():
        if m := DET_BOX.match(line.strip()):
            body = DET.match(line.strip())
            cur = [m[1], [float(m[i]) for i in range(2, 6)], [body[2].strip()] if body else []]
            out.append(cur)
        elif cur is not None and line.strip():
            cur[2].append(line.strip())
    return [layout.block(layout.label(LABELS, kind), box, (GRID, GRID),
                         " ".join(views.text(markdown.to_html(SPECIAL.sub("", "\n".join(lines)))).split()))
            for kind, box, lines in out]


def parse(raw: dict, request: contract.Request, config: UnlimitedOcr | None = None) -> tuple[dict, dict]:
    """The page and its blocks."""
    text = llm.content(raw["completion"])
    if not text.strip():
        raise errors.SystemFailed("the reply is empty", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(strip(text))
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the reply's blocks"):
                outputs["blocks"] = blocks(text)
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
