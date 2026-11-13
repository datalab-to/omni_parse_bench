"""LiteParse (run-llama/liteparse): local, model-free parsing of a PDF's text layer, with built-in Tesseract
OCR for pages or images that have none, run through its Python package.
"""
from __future__ import annotations

import dataclasses
import functools
import os
import threading
from importlib import metadata
from pathlib import Path
from typing import Any, ClassVar

from ... import markdown
from .. import contract, errors, layout
from ..adapter import Parser

SUPPORTS = frozenset({"html", "blocks"})
# LiteParse's block kinds (`LayoutBlock.kind`) onto views.LABELS. `grid_fallback` is text laid out on a grid
# that wasn't read as a table. `rule` blocks carry no text and are left out.
LABELS = {
    "heading": "heading", "paragraph": "text", "grid_fallback": "text", "list_item": "list", "code": "code",
    "table": "table", "merged_table": "table", "figure": "figure",
}
SKIP = frozenset({"rule"})
_PARSERS: dict[LiteParse, Any] = {}
_LOCK = threading.Lock()


@dataclasses.dataclass(frozen=True)
class LiteParse(Parser):
    """LiteParse, run locally through its Python package at its defaults, headers and footers kept. One parse
    of the page answers both outputs: html is its markdown through `markdown.to_html`, and blocks are its
    layout blocks, each kind mapped by LABELS. With `ocr` on (LiteParse's default), Tesseract reads the pages
    and images with no text layer; with it off, only the PDF's text layer is read. Pages are parsed in
    LiteParse's own pool of worker processes, one per worker thread. It costs nothing (`usd` 0.0) and needs no
    key, only the package:

        pip install liteparse
        opb init liteparse > config.yaml
        opb run --config config.yaml --set rows.sample=20
    """

    ocr: bool = dataclasses.field(default=True, metadata={
        "help": "OCR pages and images with no text layer (Tesseract); off reads the text layer alone"})
    ocr_language: str = dataclasses.field(default="eng", metadata={"help": "Tesseract's language"})
    headers_footers: bool = dataclasses.field(default=True, metadata={
        "help": "keep running headers and footers in the markdown (LiteParse's default strips them)"})

    name: ClassVar[str] = "liteparse"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = os.cpu_count() or 1

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: LiteParse) -> list[contract.Request]:
    """One parse answers both outputs."""
    if not wants: return []
    return [contract.Request(frozenset(wants) & SUPPORTS, {
        "ocr": config.ocr, "ocr_language": config.ocr_language, "headers_footers": config.headers_footers,
        "output_format": "markdown", "extract_blocks": True})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: LiteParse | None = None) -> contract.Call:
    """Parses the page; the answer is its markdown, its frame and its blocks, as plain data."""
    config = config or LiteParse()
    lp = parser(config, timeout)
    import liteparse
    try:
        result = lp.parse(page)
    except liteparse.ParseTimeoutError as exc:
        raise errors.SystemTimeout(str(exc)) from exc
    except liteparse.ParseError as exc:
        raise errors.SystemFailed(f"liteparse failed: {exc}", status=None) from exc
    if not result.pages:
        raise errors.SystemFailed("liteparse returned no pages", status=None)
    p = result.pages[0]
    return contract.Call({"markdown": p.markdown or "", "width": p.width, "height": p.height,
                          "blocks": [dataclasses.asdict(b) for b in p.blocks or []], "version": version()},
                         cost=contract.Cost(usd=0.0))


def parse(raw: dict, request: contract.Request, config: LiteParse | None = None) -> tuple[dict, dict]:
    """html from the markdown; blocks in reading order, boxes divided by the page's frame."""
    outputs = {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"])
    if "blocks" in request.outputs:
        frame = (raw["width"], raw["height"])
        outputs["blocks"] = [
            layout.block(layout.label(LABELS, b["kind"]), corners(b["bbox"]), frame, block_text(b))
            for b in raw["blocks"] if b["kind"] not in SKIP and b.get("bbox")]
    return outputs, {}


def corners(r: dict) -> tuple[float, float, float, float]:
    """A LiteParse box (`x`, `y`, `width`, `height`) as `[x0, y0, x1, y1]`."""
    return r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]


def block_text(b: dict) -> str:
    """A block's text: its text, its lines, or a table's cells row by row."""
    if b.get("text"): return b["text"]
    if b.get("lines"): return "\n".join(b["lines"])
    rows = ([b["header"]] if b.get("header") else []) + (b.get("rows") or [])
    return "\n".join(" | ".join(c.get("text") or "" for c in row) for row in rows)


def parser(config: LiteParse, timeout: float) -> Any:
    """One LiteParse per config, made on the first call: a pool of `workers` processes, safe to share
    between threads, its parse deadline the first call's time (the run's `timeout`)."""
    with _LOCK:
        if config not in _PARSERS:
            try:
                from liteparse import LiteParse as _LiteParse
            except ImportError as exc:
                raise FileNotFoundError("liteparse isn't installed: pip install liteparse") from exc
            _PARSERS[config] = _LiteParse(
                ocr_enabled=config.ocr, ocr_language=config.ocr_language,
                keep_headers_footers=config.headers_footers, output_format="markdown", extract_blocks=True,
                quiet=True, num_workers=1, pool_size=config.workers, parse_timeout=timeout)
        return _PARSERS[config]


@functools.cache
def version() -> str:
    """The liteparse package's version, recorded with each answer."""
    return f"liteparse {metadata.version('liteparse')}"
