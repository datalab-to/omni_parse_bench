"""PyMuPDF4LLM (pymupdf/RAG): a PDF's text layer as Markdown, with typed layout boxes, run locally on the CPU.

License: PyMuPDF, which since 2.x holds the 4LLM and layout code (the `pymupdf4llm` and `pymupdf-layout`
packages are empty shims that pull it), is dual-licensed, GNU AGPL-3.0 or an Artifex commercial license. OPB
uses it under the AGPL-3.0 and never ships it: it is an optional extra, installed by the person who runs it.
Its layout model's weights (ONNX, shipped in the wheel) carry the same license. Pinned: pymupdf4llm 2.1
(`pip install 'omni-parse-bench[pymupdf4llm]'`).
"""
from __future__ import annotations

import dataclasses
import json
import os
import signal
import subprocess
import sys
import re
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors, layout
from ..adapter import Parser

SUPPORTS = frozenset({"html", "blocks"})
# PyMuPDF4LLM's layout classes (the `class_list` of its layout model, pymupdf/layout/resources/onnx/
# layout_rf2.4.1.yaml, which `to_json` gives as each box's `boxclass`) onto views.LABELS. Every class is
# mapped: each is plainly the same kind as its label. The model has no class for code, a form or a key-value
# pair, so it never gives them.
LABELS = {
    "text": "text", "title": "heading", "section-header": "heading", "list-item": "list",
    "page-header": "page_furniture", "page-footer": "page_furniture", "footnote": "footnote",
    "caption": "caption", "formula": "equation", "table": "table", "picture": "figure",
}
# PyMuPDF documents that it isn't thread-safe; keep one page per worker. Each page is isolated in a child.
_SPACE = re.compile(r"\s+")


@dataclasses.dataclass(frozen=True)
class PyMuPDF4LLM(Parser):
    """PyMuPDF4LLM, two rows: `pymupdf4llm`, its text layer alone (`use_ocr=False`, the documented option of
    `to_markdown`/`to_json`), and `pymupdf4llm-ocr`, its default (`use_ocr=True`). Calls are
    `pymupdf4llm.to_markdown(page)` for html and `pymupdf4llm.to_json(page)` for blocks (its layout boxes,
    each with a class), with the package's other defaults: the layout engine on (`pymupdf4llm/__init__.py`:
    "Always attempt to use Layout by default"), headers and footers kept (`header=True, footer=True`), tables
    as Markdown, and images neither written nor embedded.

    OCR mode depends on the machine: the package OCRs a page that has no text layer (an image page, a
    scanned PDF page) with RapidOCR when it is installed, else with the `tesseract` binary when that is on
    the PATH, else not at all. This adapter installs neither engine. The answer records `tesseract` and
    `rapidocr`, whether each was available. The text-layer row never OCRs, so an image page is empty.

    How a page is processed:

    1. `to_markdown(page)` reads the page (a PDF page, or an image file, which PyMuPDF opens as a one-page
       document); for html, its Markdown goes through `markdown.to_html`, a format change only, recorded in
       `sent` as `derived`;
    2. `to_json(page)` gives the layout boxes, in points on the page's own size; its complete JSON answer is
       retained in the call record; blocks use each box's class, box, text lines and table cell text; and
    3. blocks are each box's class through `LABELS` and its box divided by the page's size, with the text of
       its lines (a table's cells) joined by single spaces.

    Import, version lookup, OCR setup and extraction run in one killable subprocess under the page's shared
    time budget; a timeout is a `SystemTimeout`. A call that raises fails the page. It costs nothing (`usd`
    0.0), needs no key, and runs one page at a time:

        pip install 'omni-parse-bench[pymupdf4llm]'
        opb init pymupdf4llm > config.yaml
        opb run --config config.yaml --set rows.sample=20
        opb run --config config.yaml --set system.pymupdf4llm.use_ocr=true     # the OCR row
    """

    use_ocr: bool = dataclasses.field(default=False, metadata={
        "help": "the package's `use_ocr` (its own default is True): False is the text-layer row; True OCRs a "
                "page with no text layer, if an OCR engine (RapidOCR or the tesseract binary) is installed"})

    name: ClassVar[str] = "pymupdf4llm"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = 1

    @property
    def provider(self) -> str:
        """One adapter, two rows: the text-layer mode and the OCR mode are filed apart."""
        return self.name + "-ocr" if self.use_ocr else self.name

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: PyMuPDF4LLM) -> list[contract.Request]:
    """One call per output wanted: `to_markdown` for html, `to_json` for blocks."""
    out = []
    if "html" in wants:
        derived = {"html": "PyMuPDF4LLM's markdown, through markdown.to_html"}
        sent = {"function": "to_markdown", "use_ocr": config.use_ocr, "derived": derived}
        out.append(contract.Request(frozenset({"html"}), sent))
    if "blocks" in wants:
        sent = {"function": "to_json", "use_ocr": config.use_ocr}
        out.append(contract.Request(frozenset({"blocks"}), sent))
    return out


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: PyMuPDF4LLM | None = None) -> contract.Call:
    """Run the package's function on the page; the answer is its markdown, or its boxes, and the engines."""
    fn, use_ocr = request.sent["function"], request.sent["use_ocr"]
    deadline = budget.Budget(timeout)
    script = r'''import contextlib, importlib.metadata, importlib.util, json, shutil, sys
fn, page, use_ocr = sys.argv[1], sys.argv[2], sys.argv[3] == "1"
try:
    with contextlib.redirect_stdout(sys.stderr):
        import pymupdf4llm
        p4v = importlib.metadata.version('pymupdf4llm')
        pmv = importlib.metadata.version('pymupdf')
        version = f"pymupdf4llm {p4v} (pymupdf {pmv})"
        engines = {"rapidocr": importlib.util.find_spec("rapidocr") is not None,
                   "tesseract": shutil.which("tesseract") is not None}
except (ModuleNotFoundError, importlib.metadata.PackageNotFoundError) as exc:
    print(json.dumps({"setup_error": {"type": type(exc).__name__, "name": getattr(exc, "name", None),
                                      "message": str(exc)}}))
    sys.exit(2)
with contextlib.redirect_stdout(sys.stderr):
    answer = getattr(pymupdf4llm, fn)(page, use_ocr=use_ocr)
print(json.dumps({"version": version, "engines": engines, "answer": answer}))'''
    out = run_python(script, [fn, str(page), "1" if use_ocr else "0"], deadline, fn)
    if out.returncode:
        try:
            setup_error = json.loads(out.stdout).get("setup_error", {})
        except json.JSONDecodeError:
            setup_error = {}
        if (setup_error.get("type") == "PackageNotFoundError" or
                setup_error.get("name") in {"pymupdf4llm", "pymupdf"}):
            raise FileNotFoundError(
                "pymupdf4llm isn't installed or importable: pip install 'omni-parse-bench[pymupdf4llm]'")
        raise errors.SystemFailed(f"pymupdf4llm.{fn} failed on the page: {out.stderr.strip()}", status=None)
    result = json.loads(out.stdout)
    raw: dict = {"version": result["version"], "engines": result["engines"]}
    if fn == "to_markdown":
        raw["markdown"] = result["answer"]
    else:
        raw["json"] = result["answer"]
    return contract.Call(raw, cost=contract.Cost(usd=0.0))


def run_python(script: str, args: list[str], deadline: budget.Budget,
               stage: str) -> subprocess.CompletedProcess:
    """Run vendor setup and page work within the remaining budget; kill child processes on timeout."""
    command = [sys.executable, "-c", script, *args]
    proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                            errors="replace", start_new_session=True)
    try:
        stdout, stderr = proc.communicate(timeout=deadline.remaining())
    except subprocess.TimeoutExpired as exc:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        proc.communicate()
        raise errors.SystemTimeout(f"pymupdf4llm {stage} ran past the call's {deadline.total:g} s") from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def trimmed(page: dict) -> dict:
    """The page's size and its boxes' class, box, lines of text and, for a table, cells' text: what blocks
    are made of, without the fonts and word lists."""
    boxes = []
    for b in page["boxes"]:
        lines = [_SPACE.sub(" ", "".join(s["text"] for s in line["spans"])).strip()
                 for line in b.get("textlines") or []]
        if b.get("table"):
            lines += [_SPACE.sub(" ", " ".join(str(c) for c in row if c)).strip()
                      for row in b["table"].get("extract") or []]
        boxes.append({"boxclass": b["boxclass"], "bbox": [b["x0"], b["y0"], b["x1"], b["y1"]],
                      "lines": [x for x in lines if x]})
    return {"width": page["width"], "height": page["height"], "boxes": boxes}


def parse(raw: dict, request: contract.Request, config: PyMuPDF4LLM | None = None) -> tuple[dict, dict]:
    """html from the markdown, or blocks from the layout boxes."""
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html":
            outputs[o] = markdown.to_html(raw["markdown"])
        if o == "blocks":
            try:
                with adapter.reading("pymupdf4llm's to_json answer and layout boxes"):
                    page = trimmed(json.loads(raw["json"])["pages"][0])
                    outputs[o] = layout_blocks(page)
            except errors.SystemFailed as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs


def layout_blocks(page: dict) -> list[dict]:
    """The page's boxes as the `blocks` output, in the page's own frame."""
    frame = (page["width"], page["height"])
    return [layout.block(layout.label(LABELS, b["boxclass"]), b["bbox"], frame, " ".join(b["lines"]))
            for b in page["boxes"]]
