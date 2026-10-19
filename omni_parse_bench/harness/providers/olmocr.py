"""olmOCR 2 (allenai/olmOCR-2-7B-1025-FP8), served from providers/serve/olmocr/ on any GPU host.

The adapter is `OlmOcr`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from ... import markdown
from .. import contract, errors, http
from ..adapter import PageAdapter

SUPPORTS = frozenset({"html"})
WEIGHTS = "allenai/olmOCR-2-7B-1025-FP8"


@dataclasses.dataclass(frozen=True)
class OlmOcr(PageAdapter):
    """Where the olmOCR 2 server (serve/olmocr/) answers, and the pipeline's arguments it sets (its
    defaults by default).

    Run as its own pipeline runs it (github.com/allenai/olmocr at f7cfe4c, olmocr/pipeline.py): each page
    goes through the pipeline's own `process_page`. Steps 1 to 4 run on the server (serve/olmocr/server.py);
    step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. The pipeline renders a PDF with pdftoppm at its
                              `--target_longest_image_dim` default, a 1288 px long edge; an image file is
                              made a one-page PDF first (`convert_image_to_pdf_bytes`), then rendered the
                              same way.
      2. Image preprocessing  none further; a page the model says is not upright is turned by its
                              `rotation_correction` and asked again.
      3. Model inference      vLLM 0.11.2 as the pipeline serves it (16384-token context, no video); the
                              `build_no_anchoring_v4_yaml_prompt` before the image, at most 8000 tokens. A
                              reply stands when it finished, stayed within the context and its front matter
                              type-checks as the pipeline's PageResponse; otherwise the page is asked again,
                              up to 8 attempts, at the pipeline's temperatures (0.1, 0.1, 0.2, 0.3, 0.5,
                              0.8, 0.9, 1.0).
      4. Vendor output parsing  the pipeline's FrontMatterParser: the front matter read into its
                              PageResponse, the page after it as `natural_text`.
      5. Mapping to opb outputs  html is `natural_text` through `markdown.to_html`. The model draws no
                              layout boxes: `html` only.

    Differences from the vendor:

      - the pipeline's last resort, the PDF's own text layer (pdftotext) for a page no attempt read, is a
        failed page here: that is not the model reading the page;
      - the attempts run one after another: the pipeline fires its remaining ones in parallel when the vLLM
        it launched reports an empty queue, a count this server can't see; and
      - each page has the benchmark's 900 s.

        docker build -t opb-olmocr omni_parse_bench/harness/providers/serve/olmocr
        docker run --gpus all -p 8001:8001 opb-olmocr
        opb run --providers olmocr --options '{"olmocr": {"base_url": "http://localhost:8001"}}' --sample 20

    OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
    """

    base_url: str = "http://127.0.0.1:8001"
    target_longest_image_dim: int = 1288
    max_page_retries: int = 8

    name: ClassVar[str] = "olmocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: OlmOcr) -> list[contract.Request]:
    """One call: the page as markdown."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "pipeline": "olmocr f7cfe4c, process_page", "settings": http.settings(config),
            "page": "the file, rendered by the pipeline (pdftoppm)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: OlmOcr) -> contract.Call:
    raw = http.parse(config, page, timeout)
    return contract.Call(raw, cost=contract.Cost(tokens_in=raw.get("input_tokens"),
                                                 tokens_out=raw.get("output_tokens")))


def parse(raw: dict, request: contract.Request, config: OlmOcr | None = None) -> tuple[dict, dict]:
    """The pipeline's `natural_text`, as html."""
    if raw.get("is_fallback"):
        raise errors.VendorError("no attempt read the page (the pipeline would fall back to the PDF's own "
                                 "text layer)", status=200)
    return {o: markdown.to_html(raw.get("natural_text") or "") for o in request.outputs}, {}
