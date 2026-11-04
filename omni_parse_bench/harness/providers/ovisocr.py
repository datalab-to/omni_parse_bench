"""OvisOCR (ATH-MaaS/OvisOCR), served from providers/serve/ovisocr/ on any GPU host."""
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
# The card's prompt lives in the server (serve/ovisocr/server.py, which imports nothing of ours); its
# hash names the run, and a test checks it is the server's.
PROMPT_SHA = "dbf31d5899a8"
WEIGHTS = "ATH-MaaS/OvisOCR@7b4601993131f971fb68363789ed17f55172096d"


@dataclasses.dataclass(frozen=True)
class OvisOcr(Served):
    """Where the OvisOCR server (serve/ovisocr/) answers, and the model card's settings.

    Run as its model card runs it (huggingface.co/ATH-MaaS/OvisOCR, "Inference": the `OvisOCRParser`).
    Steps 3 and 4 run on the server (serve/ovisocr/server.py); steps 1 and 5 run here.

    How a page is processed:

      1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the card takes images
                              only, so the page is rendered as for every model without a renderer of its
                              own.
      2. Image preprocessing  the model's own image processor, in vLLM, with the card's `min_pixels` 448*448
                              and `max_pixels` 2880*2880.
      3. Model inference      vLLM 0.18.1 with `trust_remote_code`, as the card runs it, the weights at
                              the revision pinned in serve/ovisocr/start.sh; the card's `<image>` and
                              newline, then its prompt, thinking off, temperature 0, at most 16384 tokens;
                              asked once. The card's offline `LLM` is asked here
                              through vLLM's OpenAI-compatible server, with the weights' own sampling
                              defaults off (`--generation-config vllm`).
      4. Vendor output parsing  the card's `parse`: the reply stripped, blocks that are only a visual
                              region's `<img src="images/bbox_...">` tag dropped (`filter_imgtags`, on by
                              default as in the card), then its `_clean_truncated_repeats`.
      5. Mapping to opb outputs  html is the reply through `markdown.to_html`. The model draws no typed
                              layout: `html` only.

    Differences from the vendor:

      - the model is asked through vLLM's server rather than the card's offline `LLM`, which is the same
        model, prompt and sampling, but another entry point; and
      - the page image is opb's PNG, not the card's own file load.

        docker build -t opb-ovisocr omni_parse_bench/harness/providers/serve/ovisocr
        docker run --gpus all -p 8001:8001 opb-ovisocr
        opb init ovisocr > config.yaml
        opb run --config config.yaml --set system.ovisocr.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "ATH-MaaS/OvisOCR",
                                 "revision": "7b4601993131f971fb68363789ed17f55172096d"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    max_tokens: int = 16384
    min_pixels: int = 448 * 448
    max_pixels: int = 2880 * 2880
    filter_imgtags: bool = dataclasses.field(default=True, metadata={
        "help": "drop blocks that are only a visual region's image tag, as the card's `parse` does"})
    long_edge: int = dataclasses.field(default=llm.LONG_EDGE, metadata={"local": True})

    name: ClassVar[str] = "ovisocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "ovisocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: OvisOcr) -> list[contract.Request]:
    """One call, for the page as markdown; the model draws no typed layout."""
    if "html" not in wants: return []
    sent = {"weights": WEIGHTS, "prompt_sha": PROMPT_SHA, "settings": http.settings(config),
            "page": "llm png"}
    return [contract.Request(frozenset({"html"}), sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: OvisOcr) -> contract.Call:
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "settings": http.settings(config)}
    return contract.Call(http.parse(config, page, timeout, body=body))


def parse(raw: dict, request: contract.Request, config: OvisOcr | None = None) -> tuple[dict, dict]:
    """The server's cleaned reply as the page."""
    return {"html": markdown.to_html(raw["text"] or "")}, {}
