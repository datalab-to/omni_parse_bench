"""MarkItDown (microsoft/markitdown): a PDF's text layer as Markdown, run locally on the CPU.

License: the package is MIT; its PDF dependencies are pdfminer.six (MIT) and pdfplumber (MIT). It has no model
weights at its defaults. Pinned: markitdown 0.1.9 (`pip install 'omni-parse-bench[markitdown]'`).
"""
from __future__ import annotations

import dataclasses
import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, ClassVar

from ... import markdown
from .. import budget, contract, errors
from ..adapter import Parser

SUPPORTS = frozenset({"html"})


@dataclasses.dataclass(frozen=True)
class MarkItDown(Parser):
    """MarkItDown at its documented defaults: `MarkItDown().convert(path).markdown`, no LLM client, no
    Document Intelligence endpoint and no plugins (its README: "plugins are disabled by default"; an LLM
    client or `docintel_endpoint` is what turns on image descriptions and OCR, and none is given). html only:
    it returns Markdown with no regions or boxes, so its layout family is 0.

    How a page is processed:

    1. a PDF page goes to `MarkItDown().convert(page)` in a subprocess; that is its text layer through
       pdfminer.six (tables through pdfplumber), with no OCR, so a scanned PDF page without a text layer is
       empty (a scan with an embedded OCR layer has text);
    2. an image page goes through the same call, whose image converter, with no LLM client, writes only the
       file's EXIF metadata, and only when `exiftool` is installed: with it absent the image is an empty
       page, and the answer records whether it was (`exiftool`); and
    3. the Markdown is turned into html by `markdown.to_html`, the one converter every provider's markdown
       goes through: a format change only, recorded in `sent` as `derived`.

    The version lookup and conversion share the page's time budget; timeout is a `SystemTimeout`. Conversion
    runs in a killable process group so a timed-out `exiftool` child is stopped too. A conversion that raises
    (a file it can't read) fails the page. It costs nothing (`usd` 0.0) and needs no key:

        pip install 'omni-parse-bench[markitdown]'
        opb init markitdown > config.yaml
        opb run --config config.yaml --set rows.sample=20
    """

    name: ClassVar[str] = "markitdown"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = min(8, os.cpu_count() or 1)

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: MarkItDown) -> list[contract.Request]:
    """One call, for html."""
    derived = {"html": "MarkItDown's markdown, through markdown.to_html"}
    return [contract.Request(wants & SUPPORTS, {"derived": derived})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: MarkItDown | None = None) -> contract.Call:
    """Convert the page; the answer is its Markdown, the package version and whether exiftool was there."""
    deadline = budget.Budget(timeout)
    ver = version(deadline)
    script = ("import json,shutil,sys; from markitdown import MarkItDown; "
              "result=MarkItDown().convert(sys.argv[1]); "
              "print(json.dumps({'markdown': result.markdown, "
              "'exiftool': shutil.which('exiftool') is not None}))")
    out = run_python(script, [str(page)], deadline, "conversion")
    if out.returncode:
        if "ModuleNotFoundError" in out.stderr or "ImportError" in out.stderr:
            raise FileNotFoundError(
                "markitdown isn't installed or importable: pip install 'omni-parse-bench[markitdown]'")
        raise errors.SystemFailed(f"markitdown failed on the page: {out.stderr.strip()}", status=None)
    result = json.loads(out.stdout)
    answer = {"markdown": result["markdown"], "version": ver, "exiftool": result["exiftool"]}
    return contract.Call(answer, cost=contract.Cost(usd=0.0))


def parse(raw: dict, request: contract.Request, config: MarkItDown | None = None) -> tuple[dict, dict]:
    """The Markdown as html."""
    h = markdown.to_html(raw["markdown"])
    return {o: h for o in request.outputs}, {}


_VERSION: list[str] = []
_VERSION_LOCK = threading.Lock()


def version(deadline: budget.Budget) -> str:
    """The installed markitdown, looked up once within the page's deadline."""
    if _VERSION:
        return _VERSION[0]
    if not _VERSION_LOCK.acquire(timeout=max(0.0, deadline.remaining())):
        raise errors.SystemTimeout(f"markitdown version lookup ran past the call's {deadline.total:g} s")
    try:
        if not _VERSION:
            script = "from importlib.metadata import version; print(version('markitdown'))"
            out = run_python(script, [], deadline, "version lookup")
            if out.returncode:
                raise FileNotFoundError(
                    "markitdown isn't installed or importable: pip install 'omni-parse-bench[markitdown]'")
            _VERSION.append(f"markitdown {out.stdout.strip()}")
        return _VERSION[0]
    finally:
        _VERSION_LOCK.release()


def run_python(script: str, args: list[str], deadline: budget.Budget,
               stage: str) -> subprocess.CompletedProcess:
    """Run a Python child within the page deadline; kill its entire process group on timeout."""
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
        raise errors.SystemTimeout(f"markitdown {stage} ran past the call's {deadline.total:g} s") from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)
