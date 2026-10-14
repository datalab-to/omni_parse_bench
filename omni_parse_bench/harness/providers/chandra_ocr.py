"""chandra-ocr-2 (datalab-to/chandra-ocr-2), served from providers/oss/chandra/ on any GPU host.

Run as the public `chandra-ocr` package runs it (github.com/datalab-to/chandra at d4f7467). Steps 1 to 4
run on the server (oss/chandra/server.py); step 5 runs here, with no vendor code.

How a page is processed:

  1. Input loading        opb sends the page file. A PDF is loaded as the package's olmOCR-bench
                          script loads one: `load_pdf_images` at 300 DPI ("300 recommended"), its
                          form fields flattened into the page. An image file goes through
                          `load_image`, which enlarges it until its shorter side is 1536 px.
  2. Image preprocessing  `scale_to_fit`: the area capped at 3072 x 2048 px, the sides rounded to
                          the model's 28 px grid.
  3. Model inference      vLLM with the flags of the package's own launcher (scripts/vllm.py at
                          --gpu h100), the `ocr_layout` prompt after the image, temperature 0,
                          top_p 0.1, at most 12384 tokens. A reply that repeats itself, errors or is
                          cut at the token limit is asked again, up to 6 times, temperature 0.2
                          higher each time (at most 0.8), top_p 0.95.
  4. Vendor output parsing  the reply is block HTML, one top-level <div data-label data-bbox> per
                          block, boxes on a 0-1000 grid; the package's `parse_html` reads each block,
                          headers and footers kept. A reply cut on every attempt is read as it is.
  5. Mapping to opb outputs  html is the blocks' readings in order, except that a picture block
                          (PICTURES) becomes an image whose alt text is its contents (the model's
                          description, a chart's data, a diagram's mermaid): a model's account of a
                          picture is not page text (docs/providers.md). blocks are the top-level
                          divs, each label from LABELS, its box divided by 1000.

Differences from the vendor:

  - headers and footers are kept (the package drops them by default; the benchmark scores the whole
    page for every system);
  - picture contents are alt text, as for every system; and
  - each page has the benchmark's 900 s.

    docker build -t opb-chandra omni_parse_bench/harness/providers/oss/chandra
    docker run --gpus all -p 8001:8001 opb-chandra
    opb predict --provider chandra-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import re
from pathlib import Path

from ... import markdown
from .. import contract, errors, http, layout
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "datalab-to/chandra-ocr-2"
# Chandra's labels (its OCR_LAYOUT_PROMPT list, and Picture) onto views.LABELS, as the datalab
# adapter maps the same types. Blank-Page marks an empty page and holds no block.
LABELS = {
    "Text": "text", "Section-Header": "heading", "List-Group": "list", "Caption": "caption",
    "Footnote": "footnote", "Page-Header": "page_furniture", "Page-Footer": "page_furniture",
    "Equation-Block": "equation", "Code-Block": "code", "Table-Of-Contents": "text",
    "Bibliography": "text", "Table": "table", "Form": "form",
    "Image": "figure", "Figure": "figure", "Picture": "figure", "Diagram": "figure",
    "Chemical-Block": "figure", "Complex-Block": "figure",
}
_DIV = re.compile(r'<div\b[^>]*\bdata-label="([^"]*)"[^>]*>', re.I)
_BBOX = re.compile(r'data-bbox="\s*(-?[\d.]+)[\s,]+(-?[\d.]+)[\s,]+(-?[\d.]+)[\s,]+(-?[\d.]+)\s*"')
_TAG = re.compile(r"<[^>]+>")
PICTURES = ("Image", "Figure", "Picture", "Diagram", "Chemical-Block")


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the chandra-ocr-2 server (oss/chandra/) answers, and the sampling of its first attempt (the
    package's by default; a retry follows the package's schedule)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    temperature: float = 0.0
    top_p: float = 0.1
    max_tokens: int = 12384
    dpi: int = 300
    max_retries: int = 6


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "prompt": "ocr_layout", "settings": http.settings(config),
            "server": "oss/chandra",
            "page": "the file, loaded as its benchmark loads one, then scale_to_fit",
            "retries": "package: on a repeat or an error, temperature +0.2 (max 0.8), top_p 0.95"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    raw = http.parse(config, page, timeout)
    usage = raw.get("usage") or {}
    cost = contract.Cost(tokens_in=usage.get("prompt_tokens"), tokens_out=usage.get("completion_tokens"))
    # Note: a reply cut at the token limit on every attempt is kept and read, as the package reads it.
    return contract.Call(raw, cost=cost, job_id=raw["completion"].get("id"))


def blocks(html: str) -> list[dict]:
    """Each top-level block div as a block: its label from LABELS, its box on the 0-1000 grid."""
    out = []
    starts = [(m.start(), m.group(1), m.group(0)) for m in _DIV.finditer(html)]
    for i, (at, label, tag) in enumerate(starts):
        if label == "Blank-Page": continue
        box = _BBOX.search(tag)
        if not box: continue
        body = html[at + len(tag): starts[i + 1][0] if i + 1 < len(starts) else len(html)]
        text = " ".join(_TAG.sub(" ", body).split())
        out.append(layout.block(layout.label(LABELS, label), [float(v) for v in box.groups()],
                                (1000, 1000), text))
    return out


def picture(block: dict) -> str:
    """A picture block as an image whose alt text is its contents, the image's own alt text first."""
    from bs4 import BeautifulSoup

    img = BeautifulSoup(block["raw"], "html.parser").find("img")
    return markdown.alt(" ".join(filter(None, [img.get("alt", "") if img else "", block["raw"]])))


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The page from the server's blocks, pictures as alt text; the blocks from the reply. A label
    LABELS lacks fails the blocks only."""
    said = llm.content(raw["completion"])
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = "".join(picture(b) if b["label"] in PICTURES else b["html"] for b in raw["blocks"]
                                  if b["label"] != "Blank-Page")
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = blocks(said)
        except errors.VendorError as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
