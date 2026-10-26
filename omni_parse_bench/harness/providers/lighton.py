"""LightOnOCR-3 (lightonai/LightOnOCR-3-4B, -0.8B), served from providers/serve/lightonocr/ on any GPU
host."""
from __future__ import annotations

import dataclasses
import hashlib
import html
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown, views
from .. import contract, errors, http, layout
from ..adapter import Served
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
PROMPT = "grounding"

# The model card's labels onto views.LABELS, and those LightOn's own ParseBench parser also reads
# (github.com/lightonai/LightOnOCR, benchmarks/ocr_bench/providers/loocr_grounding.py).
LABELS = {
    "text": "text", "paragraph": "text", "aside_text": "text", "title": "heading", "list": "list",
    "header": "page_furniture", "footer": "page_furniture", "page_number": "page_furniture",
    "page_header": "page_furniture", "page_footer": "page_furniture",
    "footnote": "footnote", "page_footnote": "footnote", "caption": "caption", "figure_title": "caption",
    "formula": "equation", "code": "code", "table": "table",
    "image": "figure", "figure": "figure", "chart": "figure", "header_image": "figure",
    "footer_image": "figure",
}
PICTURES = frozenset({"image", "figure", "chart", "header_image", "footer_image"})
# Note: a block's content follows its placeholder on the same line or the next.
_PLACEHOLDER = re.compile(r"^!\[([a-z_]+)\+?\]\((-?[\d.]+),(-?[\d.]+),(-?[\d.]+),(-?[\d.]+)\)[ \t]*", re.M)



@dataclasses.dataclass(frozen=True)
class LightOn(Served):
    """Where the LightOnOCR-3 server (serve/lightonocr/) answers, the model it serves, and its sampling (the
    client's for LightOnOCR-3 by default, temperature as its benchmark sets it).

    Run as LightOn runs it for its own benchmark (github.com/lightonai/LightOnOCR at 36755d4, its
    `lightonocr` client and benchmarks/ocr_bench). Steps 1 to 4 run on the server
    (serve/lightonocr/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF is rendered as LightOn's benchmark renders it:
                              poppler at 400 DPI, lowered so the page fits 5M pixels ("best of a DPI x
                              max-pixels sweep"; its client's own default is a 2048 px long edge); an image
                              file goes as it is.
      2. Image preprocessing  none further: the client's `to_data_url` with no longest edge, so its 2048 px
                              default doesn't undo the benchmark's render.
      3. Model inference      vLLM 0.30.0 with the model card's flags; the image, then the `grounding`
                              prompt (the model is trained on that and the empty prompt only; `grounding`
                              also gives blocks), temperature 0.1 (its README tip and its benchmark; the
                              client's default is 0.2), top_p 1.0 (`lightonocr.models.profile`; the model
                              card's example shows 0.9), thinking off, at most 12288 tokens (its benchmark's
                              limit; the client sends none); asked once.
      4. Vendor output parsing  the client's `fix_escaped_dollars` repairs escaped math delimiters, its
                              default. The reply is markdown, each block led by a placeholder naming its
                              label and its box on a 0-1000 grid, `![title](80,70,920,140)`; the content
                              follows on the same line or the next; a label ending in `+` continues the
                              block before it.
      5. Mapping to opb outputs  html is every block's markdown in order, through `markdown.to_html`, with
                              the markup its label implies where the model gave none, as LightOn's benchmark
                              reader adds it (`_render_block`): a title as a heading, code fenced, a formula
                              without delimiters between `$$`. A picture's block (an image's description, a
                              chart's table of its data) becomes the alt text of an <img>. blocks are each
                              block's label (LABELS), box divided by 1000, and text with tags removed.

    Differences from the vendor:

      - its benchmark reader wraps every formula block in `$$`; here only one with no delimiter of its own,
        since the model writes most in `$$` already and a formula block can be a list with inline math,
        which one `$$` around it breaks.

    The server serves the 4B or the 0.8B, as its WEIGHTS say, and says which in every reply (`served`), so a
    run records which answered.

        docker build -t opb-lightonocr omni_parse_bench/harness/providers/serve/lightonocr
        docker run --gpus all -p 8001:8001 opb-lightonocr
        opb run --system lightonocr --sample 20 \\
            --options '{"base_url": "http://localhost:8001"}'
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": "lightonai/LightOnOCR-3-4B",
                                 "revision": "b71010f095dc3735de7ee6b9969bff8f8f50b39a"},
        metadata={"help": "the weights its server serves and their revision; by default its start.sh's"})
    temperature: float = 0.1
    top_p: float = 1.0
    max_tokens: int = 12288
    dpi: int = 400
    max_pixels: int = 5_000_000

    name: ClassVar[str] = "lightonocr"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "lightonocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: LightOn) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sha = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
    sent = {"prompt": PROMPT, "prompt_sha": sha,
            "page": "the file, rendered as its benchmark renders one",
            "fix_dollars": True, "settings": http.settings(config),
            "render": "loocr_grounding _render_block"}
    if "html" in wants:
        sent["derived"] = {"html": "each block's markdown joined; a picture's block as an <img>'s alt text"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: LightOn) -> contract.Call:
    raw = http.parse(config, page, timeout)
    with adapter.reading("the server's answer"):
        completion = raw["completion"]
    return contract.Call(raw, cost=llm.tokens([completion]), job_id=completion.get("id"))


def split(text: str) -> list[tuple[str, tuple[float, ...], str]]:
    """The reply's blocks as (label, box, markdown). Text before the first placeholder is a block
    with no label."""
    marks = list(_PLACEHOLDER.finditer(text))
    out = [("", (), head)] if (head := text[:marks[0].start() if marks else len(text)].strip()) else []
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(text)
        out.append((m[1], tuple(float(v) for v in m.groups()[1:]), text[m.end():end].strip()))
    return out


def _plain(md: str) -> str:
    return " ".join(views.text(markdown.to_html(md)).split())


def _alt(md: str) -> str:
    return f'<img alt="{html.escape(_plain(md))}">'


_HEADING = re.compile(r"^[ \t]*#{1,6}[ \t]+")


def render(label: str, md: str) -> str:
    """A block's markdown with the markup its label implies, where the model gave none: a formula between
    `$$`, a title as a level-1 heading, code fenced."""
    if label == "code" and not md.lstrip().startswith("```"):
        return f"```\n{md}\n```"
    if label == "title" and not _HEADING.match(md):
        return f"# {md.strip()}"
    # Note: only a formula with no math delimiter of its own. LightOn's reader wraps every formula, but
    # the model writes most in `$$` already, and a `formula` block can be a list with inline `$` math,
    # which one `$$` around it turns into a single broken equation.
    if label == "formula" and "$" not in md and not md.lstrip().startswith(("\\[", "\\(")):
        return f"$$\n{md.strip()}\n$$"
    return md


def parse(raw: dict, request: contract.Request, config: LightOn | None = None) -> tuple[dict, dict]:
    """The outputs in a finished reply, as the server repaired it."""
    llm.content(raw["completion"])
    text = raw["text"]
    if not text.strip():
        raise errors.SystemFailed("the reply is empty", status=200)
    parts = split(text)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html("\n\n".join(_alt(md) if label in PICTURES else render(label, md)
                                                       for label, _, md in parts if md))
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the reply's blocks"):
                outputs["blocks"] = [layout.block(layout.label(LABELS, label), box, (1000, 1000), _plain(md))
                                     for label, box, md in parts if label]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
