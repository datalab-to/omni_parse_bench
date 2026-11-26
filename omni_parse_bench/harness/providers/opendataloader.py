"""OpenDataLoader PDF (opendataloader-project/opendataloader-pdf), run locally on the CPU: html and blocks."""
from __future__ import annotations

import dataclasses
import json
import os
import signal
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from .. import budget, contract, errors, layout, raster
from ..adapter import Parser

SUPPORTS = frozenset({"html", "blocks"})
# Note: the package bundles the Java engine (its jar), so its version decides the parser; each answer says
# which was installed.
PACKAGE = "opendataloader-pdf==2.5.24"
# OpenDataLoader's JSON element types (its schema.json) onto views.LABELS. Left out on purpose:
#   - "text block" is a container: its children are read as blocks of their own (CONTAINERS);
#   - "list item", "table row" and "table cell" are parts of a list or a table, never blocks of their own; and
#   - "header" and "footer" are page furniture, and are read as one block each, from their children.
LABELS = {
    "paragraph": "text", "heading": "heading", "caption": "caption", "list": "list", "table": "table",
    "image": "figure", "header": "page_furniture", "footer": "page_furniture", "form field": "form",
}
CONTAINERS = frozenset({"text block"})


@dataclasses.dataclass(frozen=True)
class OpenDataLoader(Parser):
    """OpenDataLoader PDF 2.5.24 (Apache-2.0; no model weights), run locally on the CPU with its documented
    default mode: the Java engine, with no hybrid backend, so no OCR (a scan without a text layer or an image
    page is empty; a scan with an embedded OCR layer returns that text). It needs Java 11 or later, and no
    key:

        pip install 'omni-parse-bench[opendataloader]'  # and a JDK: brew install openjdk
        opb init opendataloader > config.yaml
        opb run --config config.yaml --set rows.sample=20

    How a page is processed:

      1. Input loading        PDF pages are copied as-is. An image is decoded as a canonical PNG,
                              losslessly wrapped in a one-page PDF at 72 DPI (one point per source pixel);
                              decoded pixels,
                              dimensions and RGBA alpha are preserved. The wrapper is an adapter input
                              conversion because the engine accepts PDFs only.
      2. Image preprocessing  none.
      3. Model inference      none: `opendataloader_pdf.convert` runs the engine (text layer, XY-Cut++ reading
                              order, rule-based headings, lists and tables) in one JVM per page, writing its
                              `json` and `html` outputs.
      4. Vendor output parsing  the JSON's typed elements, each with a type, a text and a box in PDF points
                              (left, bottom, right, top) of the page as displayed.
      5. Mapping to opb outputs  html is the engine's html, its body as it is; blocks are the elements
                              (LABELS), boxes divided by the page's size and flipped to start at the top
                              left. A text block is read as its children, a header or footer as one block.

    Differences from the vendor:

      - page headers and footers are kept (`furniture`, its `--include-header-footer`; the engine leaves them
        out by default), as every other adapter keeps them; and
      - images are not written out (`--image-output off`), so the html carries no image files; the images'
        regions stay in the blocks as figures; and
      - image inputs use the lossless one-page PDF wrapper described above.

    Import, version lookup, image preparation, Java startup and conversion run in a killable subprocess under
    the page budget. A timeout is `SystemTimeout` and kills the JVM child too.
    """

    furniture: bool = dataclasses.field(default=True, metadata={"help": "keep page headers and footers"})

    name: ClassVar[str] = "opendataloader"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    # One JVM per page runs in a killable subprocess group; a few separate pages can run at once.
    workers: ClassVar[int] = min(4, os.cpu_count() or 1)

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: OpenDataLoader) -> list[contract.Request]:
    """One call, for both outputs."""
    if not wants: return []
    sent = {"package": PACKAGE, "format": "json,html", "image_output": "off",
            "include_header_footer": config.furniture, "mode": "default (Java engine, no hybrid)"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: OpenDataLoader | None = None) -> contract.Call:
    """Convert the page; the answer is the engine's JSON and html, the page's size and the version."""
    deadline = budget.Budget(timeout)
    script = r'''import contextlib, importlib.metadata, json, sys, tempfile
from pathlib import Path
from omni_parse_bench.harness.providers.opendataloader import as_pdf
sent = json.loads(sys.argv[2])
try:
    with contextlib.redirect_stdout(sys.stderr):
        import opendataloader_pdf
        version = importlib.metadata.version("opendataloader-pdf")
    if version != "2.5.24":
        print(json.dumps({"version_error": version}))
        sys.exit(4)
    with contextlib.redirect_stdout(sys.stderr):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "page.pdf"
            size = as_pdf(Path(sys.argv[1]), src)
            out = Path(tmp) / "out"
            opendataloader_pdf.convert(
                input_path=str(src), output_dir=str(out), format=sent["format"],
                image_output=sent["image_output"], include_header_footer=sent["include_header_footer"],
                quiet=True, timeout=float(sys.argv[3]))
            data = json.loads((out / "page.json").read_text(encoding="utf-8"))
            html = (out / "page.html").read_text(encoding="utf-8")
except (ModuleNotFoundError, importlib.metadata.PackageNotFoundError) as exc:
    print(json.dumps({"setup_error": {"type": type(exc).__name__, "name": getattr(exc, "name", None),
                                      "message": str(exc)}}))
    sys.exit(2)
except FileNotFoundError as exc:
    if exc.filename == "java" or "java" in str(exc).lower():
        print(json.dumps({"java_error": str(exc)}))
        sys.exit(3)
    raise
print(json.dumps({"json": data, "html": html, "size": size, "version": version}))'''
    out = run_python(script, [str(page), json.dumps(request.sent), str(timeout)], deadline, "page conversion")
    if out.returncode:
        try:
            result = json.loads(out.stdout)
        except json.JSONDecodeError:
            result = {}
        if "setup_error" in result:
            setup = result["setup_error"]
            if (setup.get("type") == "PackageNotFoundError" or
                    setup.get("name") == "opendataloader_pdf"):
                raise FileNotFoundError(
                    "opendataloader-pdf isn't installed: pip install 'omni-parse-bench[opendataloader]'")
        if "java_error" in result:
            raise FileNotFoundError("java isn't installed: OpenDataLoader needs Java 11 or later")
        if "version_error" in result:
            raise RuntimeError(
                f"opendataloader-pdf {result['version_error']} is installed; this adapter is for {PACKAGE}"
            )
        raise errors.SystemFailed(f"opendataloader failed: {out.stderr.strip()}", status=None)
    return contract.Call(json.loads(out.stdout), cost=contract.Cost(usd=0.0))


def run_python(script: str, args: list[str], deadline: budget.Budget,
               stage: str) -> subprocess.CompletedProcess:
    """Run the Python engine and its Java child inside the page deadline and process group."""
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
        raise errors.SystemTimeout(
            f"opendataloader {stage} ran past the call's {deadline.total:g} s"
        ) from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def as_pdf(page: Path, dest: Path) -> tuple[float, float]:
    """Write PDF input or losslessly wrap an image at 72 DPI; return the displayed size in points."""
    import pypdfium2 as pdfium

    if page.suffix.lower() != ".pdf":
        from PIL import Image

        with Image.open(page) as im:
            im.load()
            size = im.size
        from .pdf_inspector import as_pdf as lossless_image_pdf

        lossless_image_pdf(page, dest, dpi=72.0)
        return float(size[0]), float(size[1])
    dest.write_bytes(page.read_bytes())
    with raster._LOCK:
        doc = pdfium.PdfDocument(dest)
        try:
            return tuple(float(v) for v in doc[0].get_size())
        finally:
            doc.close()


def parse(raw: dict, request: contract.Request, config: OpenDataLoader | None = None) -> tuple[dict, dict]:
    """The engine's html body as html, its elements as blocks on the page."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        with adapter.reading("the engine's html"):
            html = raw["html"]
            body = re.search(r"<body[^>]*>(.*)</body>", html, re.S | re.I)
            outputs["html"] = (body[1] if body else html).strip()
    if "blocks" in request.outputs:
        width, height = raw["size"]
        try:
            with adapter.reading("the engine's elements"):
                outputs["blocks"] = list(blocks(raw["json"]["kids"], (width, height)))
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs


def blocks(elements: list[dict], size: tuple[float, float]):
    """The blocks of a list of elements, in order: a container's children in place of it."""
    width, height = size
    for e in elements:
        if e["type"] in CONTAINERS:
            yield from blocks(e["kids"], size)
            continue
        left, bottom, right, top = e["bounding box"]
        box = (left, height - top, right, height - bottom)
        yield layout.block(layout.label(LABELS, e["type"]), box, (width, height), text_of(e))


def text_of(e: dict) -> str:
    """An element's text, its children's included, as one line."""
    parts: list[str] = []

    def walk(n: dict) -> None:
        if isinstance(n.get("content"), str):
            parts.append(n["content"])
        for key in ("kids", "list items", "rows", "cells"):
            for child in n.get(key, ()):
                walk(child)

    walk(e)
    return " ".join(" ".join(parts).split())
