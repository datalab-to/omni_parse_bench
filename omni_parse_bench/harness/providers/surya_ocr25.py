"""Surya OCR 2.5 (datalab-to/surya-ocr-2.5), served from providers/serve/surya-ocr-2.5/ on any GPU host."""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from .. import contract, http
from ..adapter import Served
from . import surya_ocr

SUPPORTS = surya_ocr.SUPPORTS
WEIGHTS = "datalab-to/surya-ocr-2.5"
PACKAGE = "surya-ocr==0.23.0"
# Surya OCR 2's labels: the package's canonical labels (surya/layout/label.py) are the same in 0.23.0.
LABELS = surya_ocr.LABELS


@dataclasses.dataclass(frozen=True)
class SuryaOcr25(Served):
    """Where the Surya OCR 2.5 server (serve/surya-ocr-2.5/) answers, and the DPI a PDF is loaded at (the
    `surya_ocr` command's, IMAGE_DPI_HIGHRES, by default).

    Run as the public `surya-ocr` package (0.23.0) runs it with its `surya_ocr` command. Steps 1 to 4 run on
    the server (serve/surya-ocr-2.5/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered by the package's `load_from_file`
                              at IMAGE_DPI_HIGHRES, 192 DPI, the resolution its command uses for
                              recognition; an image file is opened as it is.
      2. Image preprocessing  the package's own, inside its predictor (`scale_to_fit` to its pixel limits).
      3. Model inference      vLLM 0.25.1 with the flags the package's own launcher sets at
                              VLLM_GPU_TYPE=h100 (no speculation: the checkpoint has no MTP head, so the
                              launcher sets none); one full-page call through
                              `RecognitionPredictor(full_page=True)`, at the package's prompt, sampling
                              and token limit. A page whose output loops or does not parse is asked again
                              at rising temperature, up to 6 times (SURYA_FULLPAGE_REGEN, which the package
                              calls its setting for benchmarking), then falls back, as the package does, to
                              layout plus OCR per block.
      4. Vendor output parsing  the package's result: the page as layout blocks in reading order, each
                              with a canonical label, a box in the image's pixels and its HTML.
      5. Mapping to opb outputs  as Surya OCR 2's (providers/surya_ocr.py): html is the blocks' HTML in
                              reading order, page headers and footers kept, skipped (visual) blocks adding
                              no text; blocks are each block's label (LABELS) and box divided by the page
                              image's size.

    Differences from the vendor:

      - SURYA_FULLPAGE_REGEN is on (the package's default is off; it names it as the setting for
        benchmarking).

        docker build -t opb-surya-ocr-2.5 omni_parse_bench/harness/providers/serve/surya-ocr-2.5
        docker run --gpus all -p 8001:8001 opb-surya-ocr-2.5
        opb init surya-ocr-2.5 > config.yaml
        opb run --config config.yaml --set system.surya-ocr-2.5.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": "00c843e9cae45611dca0a6dc2c9bbbf2dadaaed3"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    dpi: int = 192

    name: ClassVar[str] = "surya-ocr-2.5"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "surya-ocr-2.5"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: SuryaOcr25) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "package": PACKAGE, "mode": "RecognitionPredictor(full_page=True)",
            "fullpage_regen": True,
            "settings": http.settings(config), "page": "the file, loaded as its surya_ocr command loads one"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: SuryaOcr25) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def parse(raw: dict, request: contract.Request, config: SuryaOcr25 | None = None) -> tuple[dict, dict]:
    """The page in reading order, and its blocks, read as Surya OCR 2's: the package's result is the same."""
    return surya_ocr.parse(raw, request)
