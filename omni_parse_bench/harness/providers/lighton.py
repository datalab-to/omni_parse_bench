"""LightOnOCR-3 (lightonai/LightOnOCR-3-4B, -0.8B), served from providers/oss/lighton/ on any GPU host.

Run as LightOn runs it for its own benchmark (github.com/lightonai/LightOnOCR at 36755d4, its
`lightonocr` client and benchmarks/ocr_bench). Steps 1 to 4 run on the server (oss/lighton/server.py);
step 5 runs here, with no vendor code.

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
    which one `$$` around it breaks;
  - picture contents are alt text, as for every system; and
  - each page has the benchmark's 900 s.

`model` names the model the server serves (its MODEL), so a run's name tells the two sizes apart; an
answer from another model is refused.

    docker build -t opb-lighton omni_parse_bench/harness/providers/oss/lighton
    docker run --gpus all -p 8001:8001 opb-lighton
    opb predict --provider lightonocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import hashlib
import html
import re
from pathlib import Path

from ... import markdown, views
from .. import contract, errors, http, layout
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
MODELS = ("lightonai/LightOnOCR-3-4B", "lightonai/LightOnOCR-3-0.8B")
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
class Config:
    """Where the LightOnOCR-3 server (oss/lighton/) answers, the model it serves, and its sampling (the
    client's for LightOnOCR-3 by default, temperature as its benchmark sets it)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    model: str = dataclasses.field(default=MODELS[0], metadata={"choices": list(MODELS)})
    temperature: float = 0.1
    top_p: float = 1.0
    max_tokens: int = 12288
    dpi: int = 400
    max_pixels: int = 5_000_000


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sha = hashlib.sha256(PROMPT.encode()).hexdigest()[:12]
    sent = {"model": config.model, "prompt": PROMPT, "prompt_sha": sha,
            "page": "the file, rendered as its benchmark renders one",
            "fix_dollars": True, "settings": http.settings(config),
            "render": "loocr_grounding _render_block"}
    if "html" in wants:
        sent["derived"] = {"html": "each block's markdown joined; a picture's block as an <img>'s alt text"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    raw = http.parse(config, page, timeout)
    if raw.get("model") != config.model:
        raise errors.VendorError(f"the server serves {raw.get('model')!r}, not {config.model!r}: set the "
                                 f"`model` option to the model it serves", status=200)
    return contract.Call(raw, cost=llm.tokens([raw["completion"]]), job_id=raw["completion"].get("id"))


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


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The outputs in a finished reply, as the server repaired it. A label LABELS lacks fails the
    blocks only."""
    llm.content(raw["completion"])
    text = raw["text"]
    if not text.strip():
        raise errors.VendorError("the reply is empty", status=200)
    parts = split(text)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html("\n\n".join(_alt(md) if label in PICTURES else render(label, md)
                                                       for label, _, md in parts if md))
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = [layout.block(layout.label(LABELS, label), box, (1000, 1000), _plain(md))
                                 for label, box, md in parts if label]
        except errors.VendorError as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
