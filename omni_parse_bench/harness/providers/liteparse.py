"""LiteParse (run-llama/liteparse): local parsing of a PDF's text layer, with built-in OCR for pages or images
that have none (its own ocria-nano models, or Tesseract), run through its Python package on CPU.
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
# that wasn't read as a table; `page_header` and `page_footer` come from ocria-nano's layout model. `rule`
# blocks carry no text and are left out.
LABELS = {
    "heading": "heading", "paragraph": "text", "grid_fallback": "text", "list_item": "list", "code": "code",
    "table": "table", "merged_table": "table", "figure": "figure", "page_header": "page_furniture",
    "page_footer": "page_furniture",
}
SKIP = frozenset({"rule"})
BACKENDS = frozenset({"ocria-nano", "tesseract"})
_PARSERS: dict[LiteParse, Any] = {}
_LOCK = threading.Lock()


@dataclasses.dataclass(frozen=True)
class LiteParse(Parser):
    """LiteParse, run locally through its Python package at its defaults, headers and footers kept. One parse
    of the page answers both outputs: html is its markdown through `markdown.to_html`, and blocks are its
    layout blocks, each kind mapped by LABELS. Pages are parsed in LiteParse's own pool of worker processes,
    one per worker thread. It costs nothing (`usd` 0.0) and needs no key.

    `ocr_backend` picks the engine for pages and images with no text layer:

      - ocria-nano (the default, as it is LiteParse's once pulled): LiteParse's own CPU models through ONNX
        Runtime, a line detector, script router and recognizers, and LayoutNet, a table and layout model
        that also runs on born-digital pages (with `ocr` off too). Pages are rendered at LiteParse's
        default DPI for it. The models are not in the wheel: `lit models pull ocria-nano` once.
      - tesseract: built-in Tesseract (`ocr_language`), no layout model.

    With `ocr` off, only the PDF's text layer is read.

        pip install liteparse && lit models pull ocria-nano
        opb init liteparse > config.yaml
        opb run --config config.yaml --set rows.sample=20
        opb run --config config.yaml --set system.liteparse.ocr_backend=tesseract   # the Tesseract run
    """

    ocr: bool = dataclasses.field(default=True, metadata={
        "help": "OCR pages and images with no text layer; off reads the text layer alone"})
    ocr_backend: str = dataclasses.field(default="ocria-nano", metadata={
        "help": "ocria-nano (LiteParse's own models, `lit models pull ocria-nano` first) or tesseract"})
    ocr_language: str = dataclasses.field(default="eng", metadata={
        "help": "Tesseract's language; ocria-nano finds each line's script itself"})
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
        "ocr": config.ocr, "ocr_backend": config.ocr_backend, "ocr_language": config.ocr_language,
        "headers_footers": config.headers_footers,
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
                          "blocks": [dataclasses.asdict(b) for b in p.blocks or []],
                          "version": version(config.ocr_backend)},
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
            if config.ocr_backend not in BACKENDS:
                raise ValueError(
                    f"liteparse ocr_backend is one of {sorted(BACKENDS)}, not {config.ocr_backend!r}")
            try:
                from liteparse import LiteParse as _LiteParse
            except ImportError as exc:
                raise FileNotFoundError("liteparse isn't installed: pip install liteparse") from exc
            if config.ocr_backend == "ocria-nano" and not models_version():
                raise FileNotFoundError("liteparse's ocria-nano models aren't installed: "
                                        "lit models pull ocria-nano (or set ocr_backend: tesseract)")
            _PARSERS[config] = _LiteParse(
                ocr_enabled=config.ocr, ocr_backend=config.ocr_backend, ocr_language=config.ocr_language,
                keep_headers_footers=config.headers_footers, output_format="markdown", extract_blocks=True,
                quiet=True, num_workers=1, pool_size=config.workers, parse_timeout=timeout)
        return _PARSERS[config]


@functools.cache
def version(backend: str = "tesseract") -> str:
    """The liteparse package's version, and the ocria-nano models' when they read the page, recorded with
    each answer."""
    v = f"liteparse {metadata.version('liteparse')}"
    return f"{v}, ocria-nano {models_version()}" if backend == "ocria-nano" else v


def models_version() -> str | None:
    """The installed ocria-nano package's version, or None when it isn't (completely) installed."""
    from liteparse import models
    installed = (m for m in models.list() if m.name == "ocria-nano" and m.complete)
    return next((m.version or "unknown" for m in installed), None)
