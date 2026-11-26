"""OCRia-1 (llamaindex/OCRia-1), served by vLLM from providers/serve/ocria-1/ on a GPU host."""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import itertools
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import budget, contract, errors, http, layout, raster
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "llamaindex/OCRia-1"
REVISION = "489f5fa8f63858545368b9aff44256bbea6e46bc"
# The layout detector the card's `ocria_grounding` loads (Docling's Heron, Apache-2.0), at the revision the
# box server (serve/ocria-1/boxes.py) pins.
DETECTOR = "docling-project/docling-layout-heron"
DETECTOR_REVISION = "8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
# The item types of `ocria_grounding`'s layout (its layout.py: the Heron region labels, as Docling names them,
# and the types of items placed from attention alone) onto views.LABELS, as Docling's own labels map
# (the docling adapter's table). Heron's checkboxes are dropped by `ocria_grounding` before items are made.
LABELS = {
    "Text": "text", "Document Index": "text",
    "Title": "heading", "Section-header": "heading",
    "Page-header": "page_furniture", "Page-footer": "page_furniture",
    "List-item": "list", "Caption": "caption", "Footnote": "footnote", "Formula": "equation", "Code": "code",
    "Table": "table", "Form": "form", "Key-Value Region": "form", "Picture": "figure",
}
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

    Blocks, with `layout` on: the model writes no layout, so they come from the card's experimental layout
    boxes ("Layout boxes (experimental)"), the `ocria_grounding` package of the model repository, run by the
    box server in serve/ocria-1/ (boxes.sh, boxes.py) as the card's examples/serve_boxes.py runs it: Docling's
    Heron detector finds the regions, each word of the answer is placed by its box in the PDF's text layer
    (or, on an image or a PDF without one, by the model's attention in a second, teacher-forced pass of the
    same weights under Transformers 5.22.2), and each region becomes one item holding its words. The box
    server is sent the exact page image the answer was generated from (step 2), the raw answer, and, for a
    PDF, the page itself, from which it reads the text-layer words with `ocria_grounding.pdf.page_words` at
    `dpi` and scales them by the step-2 resize, so they land in that image's pixels. Each item becomes a
    block: its type through `LABELS`, its box divided by the image's size, its markdown as plain text. Items
    with no area are left out. Without `layout`, no blocks: the html is the only output.

    Differences from the vendor:

      - the card's weights are BF16 (5.17 B parameters); vLLM loads them at its default dtype.
      - on Blackwell the vision encoder's attention is torch SDPA (serve/ocria-1/start.sh), as for the other
        Qwen3.5 providers; elsewhere vLLM's own choice.
      - the server allows the call's 900 s; the card sets no limit.
      - the box server is sent the page within the card's 4.1-megapixel budget, the image the answer came
        from, as the card asks; ParseBench's `ocria_1` pipeline renders at 300 DPI with no budget. Its
        text-layer words are read at 300 DPI and scaled by that resize.

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
    layout: bool = dataclasses.field(default=False, metadata={
        "local": True, "help": "blocks from the card's experimental layout boxes (ocria_grounding with "
                               "Docling Heron), from the box server at grounding_url"})
    grounding_url: str = dataclasses.field(default="http://127.0.0.1:8100", metadata={
        "local": True, "help": "where the box server (serve/ocria-1/boxes.sh) answers, with layout on; "
                               "several, comma-separated, take pages in turn"})

    name: ClassVar[str] = "ocria-1"
    located: ClassVar[tuple[str, ...]] = ("base_url", "grounding_url")
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
    """One call, for the page as markdown, and with `layout` on, its blocks from the box server after it; the
    model draws no layout."""
    outputs = wants & (SUPPORTS if config.layout else frozenset({"html"}))
    if not outputs: return []
    sent = {"weights": WEIGHTS, "prompt_sha256": PROMPT_SHA256,
            "settings": http.settings(config), "page": "the file at dpi, within pixels, as a PNG"}
    if "blocks" in outputs:
        sent["layout"] = {"grounding": f"{WEIGHTS}@{REVISION}", "detector": f"{DETECTOR}@{DETECTOR_REVISION}",
                          "method": "accurate-layout", "words": "the PDF's text layer, at dpi, resized"}
    return [contract.Request(outputs, sent)]


def image(page: Path, config: Ocria1) -> bytes:
    """The page as a PNG: a PDF rendered at `config.dpi`, an image read as it is, then scaled down, aspect
    kept, to at most `config.pixels` (the card's snippet: scale = min(1, sqrt(pixels / area)), Lanczos)."""
    return rendered(page, config)[0]


def rendered(page: Path, config: Ocria1) -> tuple[bytes, tuple[int, int]]:
    """`image`'s PNG, and the size of the page before it was scaled down: the frame a PDF's text-layer words
    are read in at `config.dpi`."""
    from PIL import Image

    if page.suffix.lower() == ".pdf":
        img = raster.render(page, lambda size: config.dpi / 72)
    else:
        img = Image.open(page)
    size = (img.width, img.height)
    scale = min(1.0, (config.pixels / (img.width * img.height)) ** 0.5)
    if scale < 1.0:
        img = img.convert("RGB").resize((round(img.width * scale), round(img.height * scale)),
                                        Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue(), size


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Ocria1) -> contract.Call:
    deadline = budget.Budget(timeout)
    # Note: vLLM serves the weights under `<weights>@<revision>`, so asking it which it serves names them for
    # the request and for the run's record, whatever started it.
    name, served = http.served(config.base_url, deadline)
    png, size = rendered(page, config)
    body = {"model": name,
            "messages": [{"role": "system", "content": prompt()},
                         {"role": "user", "content": [llm.image_part(png)]}],
            "temperature": config.temperature, "max_tokens": config.max_tokens,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
    body = llm.chat(f"{config.base_url.rstrip('/')}/v1", body, deadline)
    raw = {**body, "served": served, "prompt_sha256": PROMPT_SHA256}
    if "blocks" in request.outputs:
        raw["layout"] = boxes(page, png, size, llm.content(body), config, deadline)
    return contract.Call(raw, cost=llm.tokens([body]), job_id=body.get("id"))


def boxes(page: Path, png: bytes, size: tuple[int, int], answer: str, config: Ocria1,
          deadline: budget.Budget) -> dict:
    """The box server's layout for one answer: `{width, height, items: [{type, label, md, box}], served}`,
    boxes in pixels of `png`. It is sent `png` (the image the answer was generated from), the raw answer
    and, for a PDF, the page and the frame its words are read in (`size`, at `config.dpi`); an empty answer
    has no items and no call."""
    if not answer.strip():
        return {"width": None, "height": None, "items": [], "served": None}
    pdf = page.suffix.lower() == ".pdf"
    body = {"image_png_b64": base64.b64encode(png).decode("ascii"), "answer": answer,
            "pdf_b64": base64.b64encode(page.read_bytes()).decode("ascii") if pdf else None,
            "dpi": config.dpi, "render_size": list(size) if pdf else None}
    url = server(config)
    try:
        got = http.post(f"{url}/ground", body, deadline)
    except errors.SystemFailed as exc:
        # Note: the chat answer is paid for and its html stands; a box server that fails (an error status, a
        # timeout) fails the page's blocks alone, as an unreadable layout does.
        return {"error": f"{type(exc).__name__}: {exc}"[:2000], "url": url}
    except Exception as exc:
        if errors.refused(exc):
            exc.add_note(f"no box server at {url}: the connection was refused. Start it (how: "
                         "serve/ocria-1/boxes.sh), or give its address with --set "
                         "system.ocria-1.grounding_url=<its address>; then run the same command again")
        raise
    # Note: what drew the boxes is what the server says it loaded; other weights or another detector are
    # another question, so they stop the run rather than fail the page.
    said = got.get("served") or {}
    want = {"weights": WEIGHTS, "revision": REVISION, "detector": DETECTOR,
            "detector_revision": DETECTOR_REVISION, "prompt_sha256": PROMPT_SHA256}
    if {k: said.get(k) for k in want} != want:
        raise ValueError(f"the box server at {url} serves {said}, not {want}; start it from "
                         "serve/ocria-1/boxes.sh")
    return got


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
    outputs, errs = {"html": markdown.to_html(page(text))}, {}
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the box server's layout"):
                outputs["blocks"] = blocks(raw["layout"])
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs


_TURN = itertools.count()


def server(config: Ocria1) -> str:
    """The box server for the next page: `grounding_url` may name several, comma-separated, each running one
    page at a time; pages take them in turn."""
    urls = [u.strip().rstrip("/") for u in config.grounding_url.split(",") if u.strip()]
    return urls[next(_TURN) % len(urls)]


def blocks(lay: dict) -> list[dict]:
    """The box server's items as blocks: the type through `LABELS`, the box divided by the image's size,
    the markdown as the text a reader sees. An item with no area is left out."""
    if "error" in lay:
        raise errors.SystemFailed(f"the box server failed: {lay['error']}", status=200)
    frame = (lay["width"], lay["height"])
    out = []
    for it in lay["items"]:
        x0, y0, x1, y1 = it["box"]
        if x1 <= x0 or y1 <= y0: continue
        text = " ".join(views.text(markdown.to_html(page(it.get("md") or ""))).split())
        out.append(layout.block(layout.label(LABELS, it["type"]), it["box"], frame, text))
    return out
