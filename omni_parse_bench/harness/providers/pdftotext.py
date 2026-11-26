"""pdftotext (poppler-utils): the PDF's text layer in reading order, the floor of the text-layer parsers.

License: poppler, and so `pdftotext`, is GPL-2.0-or-later. It has no model weights. OPB runs the binary as a
subprocess and links nothing from it.
"""
from __future__ import annotations

import dataclasses
import html as _html
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, ClassVar

from .. import budget, contract, errors
from ..adapter import Parser

SUPPORTS = frozenset({"html"})


@dataclasses.dataclass(frozen=True)
class Pdftotext(Parser):
    """pdftotext, run locally on the page's PDF at its documented defaults: `pdftotext page.pdf -`, which
    writes the text layer in reading order, UTF-8, without `-layout` (man pdftotext: "-layout: Maintain (as
    best as possible) the original physical layout of the text. The default is to 'undo' physical layout
    (columns, hyphenation, etc.) and output the text in reading order."). It reads the text layer only; it
    does no OCR, so an image page, which has none, is an empty page, and so is a scanned PDF page
    without a text layer (a scan with an embedded OCR layer gives that layer's text). Its
    text is written as html inside `<pre>`, escaped, as Tesseract's is, and it gives no layout blocks, so its
    layout family is 0.
    A pdftotext that exits with an error fails the page with its stderr, and one past the page's time is a
    `SystemTimeout`. It costs nothing (`usd` 0.0) and needs no key, only the binary:

        brew install poppler            # or: apt install poppler-utils
        opb init pdftotext > config.yaml
        opb run --config config.yaml --set rows.sample=20

    How a page is processed:

    1. a PDF page goes to `pdftotext page.pdf -`; an image page has no text layer and gives "" with no call;
    2. its stdout, decoded as UTF-8 (bad bytes replaced), is the answer, with the version of the binary; and
    3. the text is escaped and put inside `<pre>`: a format change only, nothing in the text is edited.
    """

    name: ClassVar[str] = "pdftotext"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = min(8, os.cpu_count() or 1)

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Pdftotext) -> list[contract.Request]:
    """One call, for html."""
    return [contract.Request(wants & SUPPORTS, {})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Pdftotext | None = None) -> contract.Call:
    """The page's text layer; the answer is its text and the binary's version."""
    if page.suffix.lower() != ".pdf":
        return contract.Call({"text": "", "version": None, "note": "an image has no text layer"},
                             cost=contract.Cost(usd=0.0))
    if not shutil.which("pdftotext"):
        raise FileNotFoundError("pdftotext isn't installed: brew install poppler")
    deadline = budget.Budget(timeout)
    ver = version(deadline)
    deadline.check("pdftotext was still to run")
    try:
        out = subprocess.run(["pdftotext", str(page), "-"], capture_output=True, errors="replace", text=True,
                             timeout=deadline.remaining())
    except subprocess.TimeoutExpired as exc:
        raise errors.SystemTimeout(f"pdftotext ran past the call's {deadline.total:g} s") from exc
    if out.returncode != 0:
        raise errors.SystemFailed(f"pdftotext exited {out.returncode}: {out.stderr}", status=None)
    return contract.Call({"text": out.stdout, "version": ver}, cost=contract.Cost(usd=0.0))


def parse(raw: dict, request: contract.Request, config: Pdftotext | None = None) -> tuple[dict, dict]:
    """The text as html: escaped, inside <pre>."""
    h = "<pre>" + _html.escape(raw["text"]) + "</pre>"
    return {o: h for o in request.outputs}, {}


_VERSION: list[str] = []


def version(deadline: budget.Budget) -> str:
    """pdftotext's version line, recorded with each answer (it prints it on stderr). It is read once per
    process, within the page's time: a `pdftotext -v` past it is a `SystemTimeout`, like the page's call."""
    if not _VERSION:
        deadline.check("pdftotext's version was still to be read")
        try:
            out = subprocess.run(["pdftotext", "-v"], capture_output=True, text=True, errors="replace",
                                 timeout=deadline.remaining())
        except subprocess.TimeoutExpired as exc:
            raise errors.SystemTimeout(f"pdftotext -v ran past the call's {deadline.total:g} s") from exc
        _VERSION.append((out.stderr or out.stdout).split("\n")[0].strip())
    return _VERSION[0]
