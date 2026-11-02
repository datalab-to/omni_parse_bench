"""Xiaomi-OCR-0 whole-page parsing, served from providers/serve/xiaomi_ocr/."""
from __future__ import annotations

import base64
import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from ... import markdown
from .. import contract, http
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html"})
PROMPT_SHA = "fd7abd1ca91c"
WEIGHTS = "xiaomi-research/Xiaomi-OCR-0@bbd8cf8d21f256b3644b44cb860f3a7cecb93c30"


@dataclasses.dataclass(frozen=True)
class XiaomiOcr(Served):
    """Xiaomi-OCR-0 (0.873B), using the vendor's whole-page evaluation pipeline.

    Source: SeerRay-Lab/Xiaomi-OCR-0 at b1a9bb4c07060c453785e9151715ccda6b96f0b1,
    evaluation_pipeline/e2e_img2md.py and postprocess/document.py.

    1. Load the page as an RGB PNG, at most 2048 pixels on its long edge.
    2. Let the checkpoint's image processor preprocess it in vLLM 0.22.1.
    3. Send the vendor's document prompt, then the image, thinking disabled, temperature 0,
       top_p 0.8, presence_penalty 0, repetition_penalty 1, and at most 16384 tokens.
    4. Strip the response; apply vendor finalize_document: repeated-tail cleanup, math delimiters,
       and OTSL-to-HTML tables. The full completion is kept alongside the processed text.
    5. Convert the resulting Markdown to opb HTML with markdown.to_html. No typed layout is produced.

    Differences: opb renders PDF input; raster resizing uses opb's Pillow thumbnail (BICUBIC) rather
    than the vendor's LANCZOS. vLLM's version and container are pinned here; the vendor does not pin
    vLLM. Generation defaults are explicit (--generation-config vllm), and bf16 is enforced.
    On Blackwell, the vision encoder uses TORCH_SDPA to avoid vLLM 0.22.1's CuTe compile failure.
    The optional repetition retry is disabled, as in the vendor CLI's default. The vendor prompt
    intentionally ignores headers and footers; it is used unchanged. This is the whole-page model,
    not the separate PP-DocLayoutV3 plus region recognition pipeline. The server allows 900 seconds
    for inference, versus the vendor CLI's 600-second default; decoding settings are unchanged.

        docker build -t opb-xiaomi-ocr omni_parse_bench/harness/providers/serve/xiaomi_ocr
        docker run --gpus all -p 8001:8001 opb-xiaomi-ocr
        opb init xiaomi_ocr > config.yaml
        opb run --config config.yaml --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(default_factory=lambda: {
        "weights": "xiaomi-research/Xiaomi-OCR-0", "revision": "bbd8cf8d21f256b3644b44cb860f3a7cecb93c30"},
        metadata={"help": "checkpoint and revision served, checked against the server before a run"})
    temperature: float = 0.0
    top_p: float = 0.8
    presence_penalty: float = dataclasses.field(default=0.0, metadata={
        "help": "penalty for tokens already present in the response; vendor default is zero"})
    repetition_penalty: float = 1.0
    max_tokens: int = 16384
    long_edge: int = dataclasses.field(default=llm.LONG_EDGE, metadata={"local": True})

    name: ClassVar[str] = "xiaomi_ocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "xiaomi_ocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: XiaomiOcr) -> list[contract.Request]:
    if "html" not in wants: return []
    return [contract.Request(SUPPORTS, {"weights": WEIGHTS, "prompt_sha": PROMPT_SHA,
                                      "settings": http.settings(config), "page": "llm png"})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: XiaomiOcr) -> contract.Call:
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "settings": http.settings(config)}
    return contract.Call(http.parse(config, page, timeout, body=body))


def parse(raw: dict, request: contract.Request, config: XiaomiOcr | None = None) -> tuple[dict, dict]:
    return {"html": markdown.to_html(raw["text"])}, {}
