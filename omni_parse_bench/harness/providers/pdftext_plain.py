"""pdftext (datalab-to/pdftext, Marker's text-layer extractor): the page's embedded text, no OCR."""
from __future__ import annotations

import dataclasses
import html as _html
import json
from pathlib import Path
import subprocess
import sys
from typing import Any, ClassVar

from .. import budget, contract, errors
from ..adapter import Parser

SUPPORTS = frozenset({"html"})
PACKAGE = "pdftext==0.7.1"


@dataclasses.dataclass(frozen=True)
class PdfText(Parser):
    """pdftext: the text layer of a PDF page, html only, so its layout family is 0. It does no OCR and has no
    model: a scanned PDF page without a text layer is empty (a scan with an embedded OCR layer has text), as
    is an image file. An empty page passes a `page_near_empty` test and fails every test that asks for
    content.

    License: the code is Apache-2.0 (it is built on pypdfium2, Apache-2.0 or BSD-3); it has no model weights.

    Run as the package's `plain_text_output` runs it, with its defaults (the README's "Plain text"): no
    sorting into reading order (`sort` False), hyphens at a line's end stripped and the words joined
    (`hyphens` False). The package is not one of this package's dependencies, and pins
    `pypdfium2==5.10.1`:

        uv pip install pdftext==0.7.1
        opb init pdftext > config.yaml
        opb run --config config.yaml --set rows.sample=20

    How a page is processed:

      1. Input loading        opb sends the one-page PDF; an image file is not read (it has no text layer).
      2. Image preprocessing  none.
      3. Model inference      none; pdfium reads the text layer.
      4. Vendor output parsing  `pdftext.extraction.plain_text_output`: the page's plain text.
      5. Mapping to opb outputs  the text, escaped, inside `<pre>`, as Tesseract's is.

    Differences from the vendor: none. It costs nothing (`usd` 0.0).
    """

    name: ClassVar[str] = "pdftext"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: PdfText) -> list[contract.Request]:
    """One call, for html."""
    return [contract.Request(wants & SUPPORTS,
                             {"package": PACKAGE, "settings": {"sort": False, "hyphens": False}})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: PdfText) -> contract.Call:
    """Read the page's text layer; version lookup and extraction share the page deadline."""
    deadline = budget.Budget(timeout)
    ver = version(deadline)
    if page.suffix.lower() != ".pdf":
        return contract.Call({"text": None, "version": ver}, cost=contract.Cost(usd=0.0))
    script = ("import json,sys; from pdftext.extraction import plain_text_output; "
              "print(json.dumps(plain_text_output(sys.argv[1], sort=False, hyphens=False)))")
    try:
        out = subprocess.run([sys.executable, "-c", script, str(page)], capture_output=True, text=True,
                             errors="replace", timeout=deadline.remaining())
    except subprocess.TimeoutExpired as exc:
        raise errors.SystemTimeout(f"pdftext extraction ran past the call's {deadline.total:g} s") from exc
    if out.returncode:
        if "ModuleNotFoundError" in out.stderr or "ImportError" in out.stderr:
            raise FileNotFoundError("pdftext isn't installed or importable: uv pip install pdftext==0.7.1")
        raise errors.SystemFailed(f"pdftext failed on the page: {out.stderr}", status=None)
    return contract.Call({"text": json.loads(out.stdout), "version": ver}, cost=contract.Cost(usd=0.0))


def parse(raw: dict, request: contract.Request, config: PdfText | None = None) -> tuple[dict, dict]:
    """The text as html: escaped, inside <pre>; empty for a page with no text layer."""
    text = raw["text"] or ""
    h = "<pre>" + _html.escape(text) + "</pre>" if text.strip() else ""
    return {o: h for o in request.outputs}, {}


_VERSION: list[str] = []


def version(deadline: budget.Budget) -> str:
    """Read the package version once, bounded by the page's deadline."""
    if not _VERSION:
        script = "from importlib.metadata import version; print(version('pdftext'))"
        try:
            out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True,
                                 errors="replace", timeout=deadline.remaining())
        except subprocess.TimeoutExpired as exc:
            raise errors.SystemTimeout(
                f"pdftext version lookup ran past the call's {deadline.total:g} s") from exc
        if out.returncode:
            raise FileNotFoundError("pdftext isn't installed or importable: uv pip install pdftext==0.7.1")
        _VERSION.append(out.stdout.strip())
    return _VERSION[0]
