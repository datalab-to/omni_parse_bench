"""Unlimited-OCR 2 (baidu/Unlimited-OCR-2), served from providers/serve/unlimited-ocr-2/ on any GPU host."""
from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import contract, errors, http
from ..adapter import Served
from . import llm, unlimited

SUPPORTS = unlimited.SUPPORTS
MODEL = "baidu/Unlimited-OCR-2"
PROMPT = "<PAGE><image>Multi page parsing."
PAGE = "<PAGE>"


@dataclasses.dataclass(frozen=True)
class UnlimitedOcr2(Served):
    """Where the Unlimited-OCR 2 server (serve/unlimited-ocr-2/) answers, and its sampling (the model card's).

    Run as its model card serves it (huggingface.co/baidu/Unlimited-OCR-2 at 5632329): the vendor's SGLang
    build, shipped in the weights' repository, with the card's environment and flags. Steps 1, 3 and 4 run on
    the server (serve/unlimited-ocr-2/server.py); steps 2 and 5 run in SGLang and here.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered to PNG at 300 DPI (PyMuPDF), as the
                              card's `pdf_to_images`; an image file goes as it is.
      2. Image preprocessing  the model's own, in SGLang: one page is read in gundam (tiled) crop mode.
      3. Model inference      the image, then the prompt `<PAGE><image>Multi page parsing.` (the card's
                              prompt for one page), temperature 0, special tokens kept, the card's n-gram
                              logit processor at ngram_size 35 and window_size 128 (its values for one page),
                              its page guard at 20000 tokens, at most 8000 tokens (its tokens per page);
                              asked once.
      4. Vendor output parsing  none on the server: the reply is the page's `<PAGE>` marker, then markdown
                              in blocks as Unlimited-OCR's, each opened by
                              `<|det|>label [x0, y0, x1, y1]<|/det|>`.
      5. Mapping to opb outputs  the `<PAGE>` marker dropped, then as `unlimited.UnlimitedOcr`: html is the
                              card's post-processing through `markdown.to_html`, blocks each marker's label
                              and box.

        docker build -t opb-unlimited-ocr-2 omni_parse_bench/harness/providers/serve/unlimited-ocr-2
        docker run --gpus all --shm-size 16g -p 8001:8001 opb-unlimited-ocr-2
        opb init unlimited-ocr-2 > config.yaml
        opb run --config config.yaml --set system.unlimited-ocr-2.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": MODEL, "revision": "5632329a32e103d5f1add270681e0f5c1233c6e4"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    max_tokens: int = 8000
    dpi: int = 300
    crop_mode: bool = dataclasses.field(
        default=True,
        metadata={"help": "read the page in gundam mode (tiles); false for base mode (one global view)"})
    ngram_size: int = 35
    window_size: int = 128
    max_page_tokens: int = dataclasses.field(
        default=20000,
        metadata={"help": "the vendor's page guard: at most this many tokens per page; 0 or less for none"})

    name: ClassVar[str] = "unlimited-ocr-2"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "unlimited-ocr-2"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: UnlimitedOcr2) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sha = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
    sent = {"model": MODEL, "prompt": PROMPT, "prompt_sha": sha, "settings": http.settings(config),
            "page": "the file, loaded as the model card's client loads one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: UnlimitedOcr2) -> contract.Call:
    raw = http.parse(config, page, timeout)
    with adapter.reading("the server's answer"):
        completion = raw["completion"]
    return contract.Call(raw, cost=llm.tokens([completion]), job_id=completion.get("id"))


def page(said: str) -> str:
    """The page's text: what follows its `<PAGE>` marker, as the card's `_uocr_save_results` splits pages."""
    return said.split(PAGE, 1)[1] if PAGE in said else said


def parse(raw: dict, request: contract.Request, config: UnlimitedOcr2 | None = None) -> tuple[dict, dict]:
    """The page and its blocks."""
    text = page(llm.content(raw["completion"]))
    if not text.strip():
        raise errors.SystemFailed("the reply is empty", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(unlimited.strip(text))
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the reply's blocks"):
                outputs["blocks"] = unlimited.blocks(text)
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
