"""LiteParse (run-llama/liteparse), run locally on the CPU through its Python package: html and blocks, a
text-layer mode, a Tesseract OCR mode and an ocria-nano OCR and table-model mode, as three rows.

Based on the adapter proposed by Logan Markewich in datalab-to/omni_parse_bench#80, reworked.
"""
from __future__ import annotations

import atexit
import dataclasses
import functools
import json
import os
import signal
import subprocess
import sys
import threading
from importlib import metadata
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors, layout
from ..adapter import Parser

SUPPORTS = frozenset({"html", "blocks"})
PACKAGE = "liteparse==2.21.1"
BACKENDS = frozenset({"tesseract", "ocria-nano"})
# The model package `liteparse.models.pull` installs for the ocria-nano backend (README, "OCR with
# ocria-nano").
MODEL_PACKAGE = "ocria-nano"
# LiteParse's block kinds (`LayoutBlock.kind`, listed in the package's liteparse/types.py, plus the three that
# only the ocria-nano backend's LayoutNet emits, seen in its output and in the package's binary) onto
# views.LABELS. Only a clear equivalent is mapped:
#   heading -> heading, paragraph -> text, list_item -> list, code -> code, table -> table, figure -> figure.
#   grid_fallback -> text: the package's own name for text laid out on a grid that it did not read as a table,
#     kept as verbatim source lines. It claims no table, so the only kind it can honestly stand for is text.
#   merged_table -> table: ocria-nano's table with merged cells, carried as `rows` of cells like `table`.
#   page_header -> page_furniture and page_footer -> page_furniture: ocria-nano's own classes for a running
#     header and footer (the text-layer and Tesseract rows keep them as paragraphs, and have no such class).
# LiteParse has no class for: caption, footnote, equation (its text is a paragraph) and form. Tests of those
# kinds fail for it as they do for any system with no type for the kind. A kind not in this table (one the
# package may add) fails the page's blocks with its name (`layout.label`), to be decided by a person.
LABELS = {
    "heading": "heading", "paragraph": "text", "grid_fallback": "text", "list_item": "list", "code": "code",
    "table": "table", "merged_table": "table", "figure": "figure",
    "page_header": "page_furniture", "page_footer": "page_furniture",
}
# `rule` is a ruled line or stroke: it carries no text (`text`, `lines` and `rows` are None) and no content to
# test, so it is not a block. It stays in the saved answer.
NO_BLOCK = frozenset({"rule"})
# Note: an infrastructure setting, not a quality one: a page that takes longer is killed and fails as a
# timeout; it equals the default time per page.
PARSE_TIMEOUT = 900.0
_PARSERS: dict[LiteParse, Any] = {}
_LOCK = threading.Lock()


@dataclasses.dataclass(frozen=True)
class LiteParse(Parser):
    """LiteParse 2.21.1 (Apache-2.0), run locally on the CPU. The text-layer and Tesseract rows use no model
    weights (the text layer is read by its own code, and OCR is its built-in Tesseract, Apache-2.0). The
    ocria-nano row uses LiteParse's own model package, whose weights are NOT Apache-2.0: they are under the
    OCRia-nano-1 Model License (LlamaIndex; Open RAIL-M as modified), installed with them as `LICENSE`. It
    allows "evaluating or benchmarking the Model, by any person or organization, including publishing the
    results" (its "Research Purposes"), and bars use for any purpose by an entity with more than $2M of
    revenue or funding, or in a Competing Service, except for Research Purposes. A benchmark run is that
    use only; the weights are not redistributed, and the run's outputs are not used to train a model. It needs
    no key and costs nothing (`usd` 0.0). One parse of the page answers both outputs: html is its Markdown
    (`output_format="markdown"`) through `markdown.to_html`, and blocks are its layout blocks
    (`extract_blocks=True`, "the same decomposition the Markdown renderer consumes, exposed as
    data"; the package's `LiteParse` docstring), each kind mapped by LABELS.
    `ocr` and `ocr_backend` pick the row:

      - `False` (the default), the row `liteparse`, "LiteParse": the PDF's text layer alone
        (`ocr_enabled=False`), so a page with no text layer comes back empty; and
      - `True`, the row `liteparse-tesseract`, "LiteParse (Tesseract)": `ocr_enabled=True`, which is the
        package's default, with its Tesseract engine (`ocr_backend="tesseract"`, one of the two the README
        lists) reading what the text layer lacks, in English (`ocr_language="eng"`, the README's default); and
      - `True` with `ocr_backend="ocria-nano"`, the row `liteparse-ocria-nano`, "LiteParse (ocria-nano)":
        the README's "OCR with ocria-nano" (a CPU model package of a line detector, a script router, four
        recognizers and LayoutNet, a learned table and layout model), enabled by
        `liteparse.models.pull("ocria-nano")` once and then `ocr_backend="ocria-nano"` (its default once
        pulled). Pages render at its documented 250 DPI, and `ocr_language` is ignored (it reads each line's
        script). The adapter never pulls: a machine without the package fails before any page.

    Settings. Everything not named here is the package's default.

      - `output_format="markdown"` and `extract_blocks=True`: the outputs opb reads (README, "Markdown
        Output"; the `extract_blocks` docstring);
      - `keep_headers_footers=True`: documented in the README's configuration list ("Keep running
        headers/footers in markdown output"; the default False strips repeated page-band lines and page
        chrome). A run's html keeps a page's headers and footers (docs/providers.md), so it is turned on;
      - `ocr_backend` is always named: the README says the default backend is "ocria-nano once pulled, else
        tesseract", and that with ocria-nano pulled "LayoutNet, a learned table and layout model" also reads
        born-digital pages. Naming it ("tesseract" in the first two rows) keeps those rows the same on a
        machine that has the ocria-nano models pulled; and
      - infrastructure, not quality: `quiet=True`, `pool_size=workers` and `parse_timeout=900` (the README's
        "Worker Pool and Hard Timeouts": parses run in persistent worker processes, one parse each at a time,
        a stuck one killed at the deadline) and `num_workers=1` (OCR workers inside each process).

    LiteParse's pool is made on the first page of a run and closed when the process exits.

        pip install liteparse==2.21.1                      # the `liteparse` extra; Tesseract is built in
        opb init liteparse > config.yaml
        opb run --config config.yaml --set rows.sample=20
        opb run --config config.yaml --set system.liteparse.ocr=true --set rows.sample=20
        python -c "from liteparse import models; models.pull('ocria-nano')"   # once; read its LICENSE
        opb run --config config.yaml --set system.liteparse.ocr=true \\
            --set system.liteparse.ocr_backend=ocria-nano --set rows.sample=20

    How a page is processed:

      1. Input loading        opb sends the page file: a PDF page as it is, an image as it is (LiteParse reads
                              images; with no OCR one is an empty page).
      2. Image preprocessing  text mode: none. OCR modes: the pages OCR reads are rendered at the package's
                              default DPI for the engine (Tesseract 150, ocria-nano 250).
      3. Model inference     text mode: none. Tesseract mode: Tesseract on the pages with no text layer.
                              ocria-nano mode: its OCR on those pages, and LayoutNet's tables and layout.
      4. Vendor output parsing  the page's `markdown` and its `blocks` (kind, box, text, lines or cells).
      5. Mapping to opb outputs  html is the Markdown through `markdown.to_html`; a block's box (x, y,
                              width, height in a 72-DPI frame of the page's size) is divided by the frame,
                              its kind goes through LABELS, and its text is its `text`, its `lines`, or a
                              table's cells row by row. `rule` blocks and blocks with no box are not blocks;
                              their text is still in the html.
    """

    ocr: bool = dataclasses.field(default=False, metadata={
        "help": "false is the text-layer row, with no OCR; true is OCR for what the text layer lacks, with "
                "ocr_backend"})
    ocr_backend: str = dataclasses.field(default="tesseract", metadata={
        "choices": ["tesseract", "ocria-nano"],
        "help": "with ocr=true: the built-in OCR engine; ocria-nano needs its model package pulled and its "
                "weights license accepted"})

    def __post_init__(self):
        if self.ocr_backend not in BACKENDS:
            raise ValueError(f"ocr_backend must be one of {sorted(BACKENDS)}, not {self.ocr_backend!r}")
        if not self.ocr and self.ocr_backend != "tesseract":
            raise ValueError("ocr_backend applies with ocr=true; the text-layer row names no OCR engine")

    name: ClassVar[str] = "liteparse"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    # Note: a pool process parses one page at a time, so this is the number of pages in flight.
    workers: ClassVar[int] = os.cpu_count() or 1

    @property
    def provider(self) -> str:
        """One adapter, three rows: the text-layer, Tesseract and ocria-nano modes are filed apart."""
        return f"{self.name}-{self.ocr_backend}" if self.ocr else self.name

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
        "package": PACKAGE, "ocr_enabled": config.ocr, "ocr_backend": config.ocr_backend,
        "keep_headers_footers": True, "output_format": "markdown", "extract_blocks": True})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: LiteParse | None = None) -> contract.Call:
    """Parse in one killable process group under the page's total budget."""
    config = config or LiteParse()
    deadline = budget.Budget(timeout)
    out = run_python(_WORKER, [str(page), json.dumps(request.sent)], deadline, "page conversion")
    if out.returncode:
        try:
            result = json.loads(out.stdout)
        except json.JSONDecodeError:
            result = {}
        if "setup_error" in result:
            raise FileNotFoundError("liteparse isn't installed: pip install 'omni-parse-bench[liteparse]'")
        if "model_error" in result:
            raise FileNotFoundError(result["model_error"])
        if "version_error" in result:
            raise RuntimeError(
                f"liteparse {result['version_error']} is installed; this adapter is for {PACKAGE}"
            )
        if "timeout" in result:
            raise errors.SystemTimeout(f"liteparse timed out: {result['timeout']}")
        message = result.get("parse_error", result.get("error", out.stderr.strip()))
        raise errors.SystemFailed(f"liteparse failed: {message}", status=None)
    return contract.Call(json.loads(out.stdout), cost=contract.Cost(usd=0.0))


def run_python(script: str, args: list[str], deadline: budget.Budget,
               stage: str) -> subprocess.CompletedProcess:
    """Run imports, version/model lookup, LiteParse's pool and conversion under one killable page budget."""
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
        raise errors.SystemTimeout(f"liteparse {stage} ran past the call's {deadline.total:g} s") from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


_WORKER = r'''import contextlib, importlib.metadata, json, sys
from pathlib import Path

liteparse = None
try:
    from omni_parse_bench.harness.providers import liteparse as adapter
    installed = importlib.metadata.version("liteparse")
    if installed != "2.21.1":
        print(json.dumps({"version_error": installed}))
        sys.exit(4)
    with contextlib.redirect_stdout(sys.stderr):
        import liteparse
        sent = json.loads(sys.argv[2])
        config = adapter.LiteParse(ocr=sent["ocr_enabled"], ocr_backend=sent["ocr_backend"])
        result = adapter.parser(config).parse(Path(sys.argv[1]))
        if not result.pages:
            raise ValueError("LiteParse returned no pages")
        page = result.pages[0]
        raw = {"markdown": page.markdown or "", "width": page.width, "height": page.height,
               "blocks": [adapter.dataclasses.asdict(block) for block in page.blocks or []],
               "version": adapter.version(config.ocr, config.ocr_backend)}
except Exception as exc:
    if isinstance(exc, (ModuleNotFoundError, importlib.metadata.PackageNotFoundError)):
        print(json.dumps({"setup_error": str(exc)}))
        sys.exit(2)
    if liteparse is not None and isinstance(exc, liteparse.ParseTimeoutError):
        print(json.dumps({"timeout": str(exc)}))
        sys.exit(3)
    if liteparse is not None and isinstance(exc, liteparse.ParseError):
        print(json.dumps({"parse_error": str(exc)}))
        sys.exit(5)
    if isinstance(exc, RuntimeError) and "ocria-nano models are not installed" in str(exc):
        print(json.dumps({"model_error": str(exc)}))
        sys.exit(6)
    raise
print(json.dumps(raw))'''


def parse(raw: dict, request: contract.Request, config: LiteParse | None = None) -> tuple[dict, dict]:
    """html from the markdown; blocks in the package's reading order, boxes divided by the page's frame."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(raw["markdown"]) if raw["markdown"].strip() else ""
    if "blocks" in request.outputs:
        try:
            with adapter.reading("LiteParse's layout blocks"):
                frame = (raw["width"], raw["height"])
                outputs["blocks"] = [
                    layout.block(layout.label(LABELS, b["kind"]), corners(b["bbox"]), frame, block_text(b))
                    for b in raw["blocks"] if b["kind"] not in NO_BLOCK and b.get("bbox")]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs


def corners(r: dict) -> tuple[float, float, float, float]:
    """A LiteParse box (`x`, `y`, `width`, `height`) as `[x0, y0, x1, y1]`."""
    return r["x"], r["y"], r["x"] + r["width"], r["y"] + r["height"]


def block_text(b: dict) -> str:
    """A block's text: its text, its lines, or a table's cells row by row."""
    if b.get("text"): return b["text"]
    if b.get("lines"): return "\n".join(b["lines"])
    rows = ([b["header"]] if b.get("header") else []) + (b.get("rows") or [])
    return "\n".join(" | ".join(c.get("text") or "" for c in row) for row in rows)


def parser(config: LiteParse) -> Any:
    """The LiteParse for a config, made on its first use and shared by the worker threads: a pool of
    `workers` processes, closed at exit."""
    with _LOCK:
        if config not in _PARSERS:
            installed = metadata.version("liteparse")
            if installed != PACKAGE.split("==")[1]:
                raise RuntimeError(f"liteparse {installed} is installed; this adapter is for {PACKAGE}")
            from liteparse import LiteParse as _LiteParse

            if config.ocr_backend == "ocria-nano":
                model_version(required=True)

            _PARSERS[config] = _LiteParse(
                ocr_enabled=config.ocr, ocr_backend=config.ocr_backend, keep_headers_footers=True,
                output_format="markdown", extract_blocks=True, quiet=True, num_workers=1,
                pool_size=config.workers, parse_timeout=PARSE_TIMEOUT)
        return _PARSERS[config]


@atexit.register
def close() -> None:
    """Shut down every pool this process made."""
    with _LOCK:
        while _PARSERS:
            _PARSERS.popitem()[1].close()


def model_version(required: bool = False) -> str | None:
    """The installed ocria-nano model package's version (`liteparse.models.list`); None when it is not
    installed or incomplete, which `required` turns into an error."""
    from liteparse import models

    for m in models.list():
        if m.name == MODEL_PACKAGE and m.complete:
            return m.version
    if required:
        raise RuntimeError('the ocria-nano models are not installed: run `python -c "from liteparse import '
                           'models; models.pull(\'ocria-nano\')"` once (read its LICENSE first)')
    return None


@functools.cache
def version(ocr: bool = False, backend: str = "tesseract") -> str:
    """The package's version and the mode it ran in, recorded with each answer."""
    if not ocr: mode = "text layer, no OCR"
    elif backend == "ocria-nano": mode = f"OCR: ocria-nano {model_version()}"
    else: mode = f"OCR: {backend}"
    return f"liteparse {metadata.version('liteparse')}, {mode}"
