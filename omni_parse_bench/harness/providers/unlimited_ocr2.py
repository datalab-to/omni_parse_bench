"""Unlimited-OCR 2 (baidu/Unlimited-OCR-2), served from providers/serve/unlimited-ocr-2/ on any GPU host."""
from __future__ import annotations

import dataclasses
import hashlib
from typing import Any, ClassVar

from .. import contract, http
from . import unlimited

MODEL = "baidu/Unlimited-OCR-2"


@dataclasses.dataclass(frozen=True)
class UnlimitedOcr2(unlimited.UnlimitedOcr):
    """Where the Unlimited-OCR 2 server (serve/unlimited-ocr-2/) answers, and its sampling.

    Unlimited-OCR's successor with the same prompt, output format and recipe, so it is run and read as
    `unlimited.UnlimitedOcr` is (its docstring has the steps); only the weights differ.

        docker build -t opb-unlimited-ocr-2 omni_parse_bench/harness/providers/serve/unlimited-ocr-2
        docker run --gpus all -p 8001:8001 opb-unlimited-ocr-2
        opb init unlimited-ocr-2 > config.yaml
        opb run --config config.yaml --set system.unlimited-ocr-2.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": MODEL, "revision": "5632329a32e103d5f1add270681e0f5c1233c6e4"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})

    name: ClassVar[str] = "unlimited-ocr-2"
    SERVE: ClassVar[str | None] = "unlimited-ocr-2"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        """One call answers every output."""
        if not wants: return []
        sha = hashlib.sha256(unlimited.PROMPT.encode()).hexdigest()[:12]
        sent = {"model": MODEL, "prompt": unlimited.PROMPT, "prompt_sha": sha, "settings": http.settings(self),
                "page": "the file, loaded as its pipeline loads one"}
        return [contract.Request(frozenset(wants) & unlimited.SUPPORTS, sent)]
