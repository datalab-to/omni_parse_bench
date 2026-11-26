"""OCRia-1 (llamaindex/OCRia-1), served by vLLM from providers/serve/ocria-1/ on a GPU host."""
from __future__ import annotations

import dataclasses
import hashlib
import io
import re
from pathlib import Path
from typing import Any, ClassVar

from ... import markdown
from .. import budget, contract, errors, http, raster
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html"})
WEIGHTS = "llamaindex/OCRia-1"
REVISION = "489f5fa8f63858545368b9aff44256bbea6e46bc"
# The model card's prompt.txt at REVISION ("Use it unchanged; other prompts change the output format"), the
# system message of every call. It is fetched from the model repository when first needed, as the card does
# (hf_hub_download), and cached by the Hub client; the repository holds only its hash.
PROMPT_SHA256 = "907944f61490bf666cc93129d93d1537d9d6f872cc285c371c7889700b6f3e38"
# The model's page furniture: its own tags, each at a line of its own in the page.
_BAND = re.compile(r"</?(?:page_header|page_footer|watermark)>", re.I)
_NUMBER = re.compile(r"</?page_number>", re.I)
_FENCE = re.compile(r"[ \t]*```")
_WRAPPER = re.compile(r"[ \t]*```(?:markdown|md|html)[ \t]*", re.I)
# An image is written `![label: description]`, with no address.
_IMAGE = re.compile(r"!\[([^\]\n]*)\](?!\()")


@dataclasses.dataclass(frozen=True)
class Ocria1(Served):
    """Where the server (serve/ocria-1/) answers (its chat endpoint is vLLM's, under /v1), and the model
    card's decoding.

    Run as its model card runs it (huggingface.co/llamaindex/OCRia-1 at 489f5fa, "Quickstart", "Input" and
    "Output"). The model is LlamaIndex's, a 4B model fine-tuned from Qwen3.5-4B; the card offers no client
    beyond the chat call, so every step runs here, asking vLLM directly.

    How a page is processed:

      1. Input loading        a PDF is rendered at 300 DPI ("Render PDF pages at 300 DPI"), through the
                              harness's pdfium lock; an image file is read as it is.
      2. Image preprocessing  the card's budget of about 4.1 megapixels ("about 210 DPI for a letter page"),
                              applied as its snippet does: a page over it is scaled down, aspect kept, with
                              Lanczos, to `pixels`; a smaller one is left alone. Then the model's own image
                              processor, in vLLM. The card's "Input" section (README lines 162-163) gives
                              both: "Render PDF pages at 300 DPI" and a budget of about 4.1 megapixels.
      3. Model inference      `vllm serve` with the card's flags (`--max-model-len 32768`,
                              `--limit-mm-per-prompt '{"image": 1}'`), one image per request, the card's
                              prompt.txt (fetched from the pinned revision, sha256
                              checked) as the system message and no user text, thinking off
                              (`chat_template_kwargs: {"enable_thinking": false}`; "with it on the model
                              answers in the wrong format"), temperature 0, at most 24576 tokens; asked once.
      4. Vendor output parsing  the card says to strip the ```markdown fence; `markdown.to_html` does, and
                              keeps a fenced listing inside the page (the card's regex would end the page
                              at the first inner fence, a mermaid diagram's say).
      5. Mapping to opb outputs  html is the markdown through `markdown.to_html`: the page furniture tags
                              (`<page_header>`, `<page_footer>`, `<watermark>`) become paragraph breaks and
                              `<page_number>` is unwrapped, so each band's text stays in the page, in its
                              place; an image `![label: description]` becomes an image whose alt text is
                              `label: description`. Tables stay HTML as the model wrote them.

    No `blocks`: the model writes no layout. The card's layout boxes are an experimental, separate step,
    `ocria_grounding`, which reads a second pass of the weights under Transformers 5.22.2 (attention) with the
    Docling Heron detector, so it needs a second server and, on an image, rougher positions; this adapter
    does not run it, and its html is the only output.

    Differences from the vendor:

      - the card's weights are BF16 (5.17 B parameters); vLLM loads them at its default dtype.
      - on Blackwell the vision encoder's attention is torch SDPA (serve/ocria-1/start.sh), as for the other
        Qwen3.5 providers; elsewhere vLLM's own choice.
      - the server allows the call's 900 s; the card sets no limit.

    License: the weights are under the OCRia-1 Model and Code License (a modified OpenRAIL-M, LlamaIndex,
    Inc.; huggingface.co/llamaindex/OCRia-1/blob/main/LICENSE), not open source. Its "Research Purposes"
    include "evaluating or benchmarking the Model, by any person or organization, including publishing the
    results", which is this adapter's use. Beyond them, the license restricts an organization with more than
    $2M in revenue or funding, and any competing document-parsing service. Section 7 asks that a use credit
    LlamaIndex, link the model and give the license: OCRia-1 is by LlamaIndex,
    https://huggingface.co/llamaindex/OCRia-1, and this repository changes nothing in it. The model is a
    fine-tune of Qwen3.5-4B (Apache-2.0). No weights and no `ocria_grounding` code are in this repository;
    the license bars using the model's output to train another model except for Research Purposes.

        docker build -t opb-ocria-1 omni_parse_bench/harness/providers/serve/ocria-1
        docker run --gpus all -p 8001:8001 opb-ocria-1
        opb init ocria-1 > config.yaml
        opb run --config config.yaml --set system.ocria-1.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": WEIGHTS, "revision": REVISION},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.0
    max_tokens: int = 24576
    dpi: int = dataclasses.field(default=300, metadata={"help": "PDF render resolution (the card's)"})
    pixels: int = dataclasses.field(
        default=4_100_000, metadata={"help": "the page image's area budget in pixels (the card's)"})

    name: ClassVar[str] = "ocria-1"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "ocria-1"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)

    def server(self, *, timeout: float) -> dict[str, Any]:
        """What vLLM says it serves, read off its /v1/models: this folder runs vLLM alone, with no /served
        route."""
        try:
            return http.served(self.base_url, budget.Budget(timeout))[1]
        except Exception as exc:
            if errors.refused(exc): errors.no_server(exc, self.base_url, self.provider, self.SERVE)
            raise


def prompt() -> str:
    """The card's prompt.txt at REVISION, downloaded once (the Hub client caches it); a file whose sha256
    isn't PROMPT_SHA256 stops the run."""
    from huggingface_hub import hf_hub_download

    text = Path(hf_hub_download(WEIGHTS, "prompt.txt", revision=REVISION)).read_bytes()
    if (got := hashlib.sha256(text).hexdigest()) != PROMPT_SHA256:
        raise ValueError(f"prompt.txt of {WEIGHTS}@{REVISION} has sha256 {got}, not {PROMPT_SHA256}")
    return text.decode("utf-8")


def requests(wants: frozenset[str], config: Ocria1) -> list[contract.Request]:
    """One call, for the page as markdown; the model draws no layout."""
    if "html" not in wants: return []
    sent = {"weights": WEIGHTS, "prompt_sha256": PROMPT_SHA256,
            "settings": http.settings(config), "page": "the file at dpi, within pixels, as a PNG"}
    return [contract.Request(frozenset({"html"}), sent)]


def image(page: Path, config: Ocria1) -> bytes:
    """The page as a PNG: a PDF rendered at `config.dpi`, an image read as it is, then scaled down, aspect
    kept, to at most `config.pixels` (the card's snippet: scale = min(1, sqrt(pixels / area)), Lanczos)."""
    from PIL import Image

    if page.suffix.lower() == ".pdf":
        img = raster.render(page, lambda size: config.dpi / 72)
    else:
        img = Image.open(page)
    scale = min(1.0, (config.pixels / (img.width * img.height)) ** 0.5)
    if scale < 1.0:
        img = img.convert("RGB").resize((round(img.width * scale), round(img.height * scale)),
                                        Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Ocria1) -> contract.Call:
    deadline = budget.Budget(timeout)
    # Note: vLLM serves the weights under `<weights>@<revision>`, so asking it which it serves names them for
    # the request and for the run's record, whatever started it.
    name, served = http.served(config.base_url, deadline)
    body = {"model": name,
            "messages": [{"role": "system", "content": prompt()},
                         {"role": "user", "content": [llm.image_part(image(page, config))]}],
            "temperature": config.temperature, "max_tokens": config.max_tokens,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    body = llm.chat(f"{config.base_url.rstrip('/')}/v1", body, deadline)
    raw = {**body, "served": served, "prompt_sha256": PROMPT_SHA256}
    return contract.Call(raw, cost=llm.tokens([body]), job_id=body.get("id"))


def page(said: str) -> str:
    """The model's markdown with its tags as plain markup, outside any fenced listing: furniture bands as
    paragraphs of their own, the page number unwrapped, an image as its alt text."""
    out, fenced = [], False
    for line in said.split("\n"):
        # Note: a line inside a fenced listing (```mermaid, ```) is code, not the model's markup. The fence
        # naming the page itself (```markdown) opens no listing; `markdown.to_html` removes it.
        if _FENCE.match(line):
            fenced = fenced != (not _WRAPPER.fullmatch(line))
            out.append(line)
        elif fenced:
            out.append(line)
        else:
            line = _NUMBER.sub("", _BAND.sub("\n\n", line))
            out.append(_IMAGE.sub(lambda m: markdown.alt(m[1]), line))
    return "\n".join(out)


def parse(raw: dict, request: contract.Request, config: Ocria1 | None = None) -> tuple[dict, dict]:
    text = llm.content(raw)
    if not text.strip():
        raise errors.SystemFailed("the reply is empty", status=200)
    return {"html": markdown.to_html(page(text))}, {}
