"""OvisOCR2 (ATH-MaaS/OvisOCR2), served from providers/serve/ovisocr2/ on any GPU host."""
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
# The card's prompt lives in the server (serve/ovisocr2/server.py, which imports nothing of ours); its
# hash names the run, and a test checks it is the server's.
PROMPT_SHA = "de9617f877f6"
WEIGHTS = "ATH-MaaS/OvisOCR2@cbdede82e048659b83310476ff807da825f8fe78"


@dataclasses.dataclass(frozen=True)
class OvisOcr2(Served):
    """Where the OvisOCR2 server (serve/ovisocr2/) answers, and the model card's settings.

    Run as its model card runs it (huggingface.co/ATH-MaaS/OvisOCR2, "Inference": the `OvisOCR2Parser`).
    Steps 3 and 4 run on the server (serve/ovisocr2/server.py); steps 1 and 5 run here.

    How a page is processed:

      1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the card takes images
                              only, so the page is rendered as for every model without a renderer of its
                              own.
      2. Image preprocessing  the model's own image processor, in vLLM, with the card's `min_pixels` 448*448
                              and `max_pixels` 2880*2880.
      3. Model inference      vLLM 0.22.1 with `gdn_prefill_backend=triton`, as the card runs it, the
                              weights at the revision pinned in serve/ovisocr2/start.sh; the page image,
                              then the card's prompt (it begins with a newline), thinking off, temperature
                              0, at most 16384 tokens; asked once. The card's offline `LLM` is asked here
                              through vLLM's OpenAI-compatible server, with the weights' own sampling
                              defaults off (`--generation-config vllm`).
      4. Vendor output parsing  the card's `parse`: the reply stripped, blocks that are only a visual
                              region's `<img src="images/bbox_...">` tag dropped (`filter_imgtags`, on by
                              default as in the card), then its `_clean_truncated_repeats`.
      5. Mapping to opb outputs  html is the reply through `markdown.to_html`. The model draws no typed
                              layout: `html` only.

    Differences from the vendor:

      - on Blackwell the vision encoder's attention is torch SDPA (start.sh; `MM_ENCODER_ATTN_BACKEND`
        overrides), because vLLM 0.22.1's own choice for it, compiled at start-up, fails there; on other GPUs
        it is vLLM's choice, as the card runs it;
      - the model is asked through vLLM's server rather than the card's offline `LLM`, which is the same
        model, prompt and sampling, but another entry point; and
      - the page image is opb's PNG, not the card's own file load.

        docker build -t opb-ovisocr2 omni_parse_bench/harness/providers/serve/ovisocr2
        docker run --gpus all -p 8001:8001 opb-ovisocr2
        opb init ovisocr2 > config.yaml
        opb run --config config.yaml --set system.ovisocr2.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "ATH-MaaS/OvisOCR2",
                                 "revision": "cbdede82e048659b83310476ff807da825f8fe78"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    max_tokens: int = 16384
    min_pixels: int = 448 * 448
    max_pixels: int = 2880 * 2880
    filter_imgtags: bool = dataclasses.field(default=True, metadata={
        "help": "drop blocks that are only a visual region's image tag, as the card's `parse` does"})
    long_edge: int = dataclasses.field(default=llm.LONG_EDGE, metadata={"local": True})

    name: ClassVar[str] = "ovisocr2"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "ovisocr2"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: OvisOcr2) -> list[contract.Request]:
    """One call, for the page as markdown; the model draws no typed layout."""
    if "html" not in wants: return []
    sent = {"weights": WEIGHTS, "prompt_sha": PROMPT_SHA, "settings": http.settings(config),
            "page": "llm png"}
    return [contract.Request(frozenset({"html"}), sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: OvisOcr2) -> contract.Call:
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "settings": http.settings(config)}
    return contract.Call(http.parse(config, page, timeout, body=body))


def parse(raw: dict, request: contract.Request, config: OvisOcr2 | None = None) -> tuple[dict, dict]:
    """The server's cleaned reply as the page."""
    return {"html": markdown.to_html(raw["text"] or "")}, {}
