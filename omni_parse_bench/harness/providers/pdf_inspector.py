"""pdf-inspector (firecrawl/pdf-inspector), run locally on the CPU: html only, a text mode and an OCR mode."""
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

from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors
from ..adapter import Parser

SUPPORTS = frozenset({"html"})
# Note: the package is a compiled extension (the Rust library), so its version decides the parser; each
# answer says which was installed.
PACKAGE = "pdf-inspector==1.27.1"
OCR_MODES = ("off", "auto", "force")
# Pin the image page size to its original pixel dimensions when PDFium renders at the package's default DPI.
DPI = 150.0


@dataclasses.dataclass(frozen=True)
class PdfInspector(Parser):
    """pdf-inspector 1.27.1 (MIT; its OCR models are PP-OCRv6 Small, Apache-2.0, fetched at run time), run
    locally on the CPU. `img2pdf` 0.6.3 (LGPL-3.0) losslessly wraps image inputs as PDF pages. The vendor
    returns one Markdown string per document and no labeled regions, so html only and its layout family is 0.
    It needs no key. `ocr` picks the row:

      - `off` (the default): its text mode, `pdf_inspector.process_pdf` (README: "extracts text with position
        awareness, and converts to clean Markdown without OCR"). A scanned PDF without a text layer is empty
        (a scan with an embedded OCR layer has text); and
      - `auto` or `force`: its OCR mode, `pdf_inspector.process_pdf_with_ocr` (README: "Selective OCR ...
        run PP-OCRv6 Small locally"). `auto`, the package's default, OCRs only the pages its native
        extraction rejects; `force` OCRs every page. It needs PDFium and ONNX Runtime shared libraries and
        downloads three model files (about 31 MB, checksum-verified) on the first routed page
        (docs/ocr-runtime.md there):

            export PDFIUM_LIB_PATH=/path/to/libpdfium.dylib     # firecrawl/pdfium-rs, native-v7988
            export ORT_DYLIB_PATH=/path/to/libonnxruntime.1.27.0.dylib   # the onnxruntime 1.27.0 wheel

    The OCR mode is its own row, filed as `pdf-inspector-ocr`.

        pip install 'omni-parse-bench[pdf-inspector]'       # includes pdf-inspector and img2pdf
        opb init pdf-inspector > config.yaml
        opb run --config config.yaml --set rows.sample=20
        opb run --config config.yaml --set system.pdf-inspector.ocr=auto --set rows.sample=20

    How a page is processed:

      1. Input loading        a PDF page goes to the package as it is. An image (which the package's PDF-only
                              API does not accept) is decoded and rewritten as a canonical PNG, then wrapped
                              by `img2pdf` losslessly at 150 DPI and its original pixel dimensions; RGBA
                              alpha is retained as a PDF soft mask.
      2. Image preprocessing  text mode: none. OCR mode: a routed page is rendered by PDFium at `dpi` (150).
      3. Model inference      text mode: none; the package reads the page's text layer. OCR mode: PP-OCRv6
                              Small (detection, recognition) on the routed pages, native text elsewhere.
      4. Vendor output parsing  the package's Markdown for the page.
      5. Mapping to opb outputs  html is the Markdown through `markdown.to_html`.

    No setting differs from the package's own: the call is `process_pdf(path)` or
    `process_pdf_with_ocr(path, mode=ocr)`.
    """

    ocr: str = dataclasses.field(default="off", metadata={
        "help": "off is the text mode, with no OCR; auto OCRs the pages its native extraction rejects; "
                "force OCRs every page"})

    name: ClassVar[str] = "pdf-inspector"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    # Note: the OCR runtime is loaded once per process and runs on the CPU's threads itself.
    workers: ClassVar[int] = min(4, os.cpu_count() or 1)

    def __post_init__(self) -> None:
        if self.ocr not in OCR_MODES:
            raise ValueError(f"ocr is one of {', '.join(OCR_MODES)}, not {self.ocr!r}")

    @property
    def provider(self) -> str:
        """One adapter, two rows: the text mode and the OCR mode are filed apart."""
        return self.name if self.ocr == "off" else self.name + "-ocr"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: PdfInspector) -> list[contract.Request]:
    """One call, for html."""
    if not wants: return []
    sent = {"package": PACKAGE, "function": "process_pdf" if config.ocr == "off" else "process_pdf_with_ocr",
            "ocr": config.ocr}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: PdfInspector | None = None) -> contract.Call:
    """Process the page; the answer is its Markdown, its type and, in OCR mode, the pages OCR read."""
    config = config or PdfInspector()
    deadline = budget.Budget(timeout)
    installed = version(deadline)
    if installed != PACKAGE.split("==")[1]:
        raise RuntimeError(f"pdf-inspector {installed} is installed; this adapter is for {PACKAGE}")
    script = r'''import json, sys, tempfile
from pathlib import Path
import pdf_inspector
from omni_parse_bench.harness.providers.pdf_inspector import as_pdf
page, ocr, dpi = Path(sys.argv[1]), sys.argv[2], float(sys.argv[3])
with tempfile.TemporaryDirectory() as tmp:
    src = Path(tmp) / "page.pdf"
    as_pdf(page, src)
    if ocr == "off":
        got = pdf_inspector.process_pdf(str(src))
        raw = {"markdown": got.markdown, "pdf_type": got.pdf_type, "confidence": got.confidence}
    else:
        got = pdf_inspector.process_pdf_with_ocr(str(src), mode=ocr)
        raw = {"markdown": got.markdown, "routed_to_ocr": list(got.pages_routed_to_ocr),
               "pages": [{"page": p.page_number, "source": p.provenance.source,
                          "confidence": p.provenance.ocr_confidence} for p in got.pages]}
print(json.dumps(raw))'''
    out = run_python(script, [str(page), config.ocr, str(DPI)], deadline, "page extraction")
    if out.returncode:
        if any(f"No module named '{module}'" in out.stderr for module in
               ("pdf_inspector", "img2pdf", "pikepdf")):
            raise FileNotFoundError(
                "pdf-inspector isn't installed or importable: pip install 'omni-parse-bench[pdf-inspector]'")
        runtime_markers = ("pdfium", "onnxruntime", "ort_dylib_path", "pdfium_lib_path", "dlopen")
        if config.ocr != "off" and any(x in out.stderr.lower() for x in runtime_markers):
            raise RuntimeError("pdf-inspector OCR runtime is unavailable; install PDFium and ONNX Runtime "
                               "1.27.0 and set PDFIUM_LIB_PATH and ORT_DYLIB_PATH. " + out.stderr.strip())
        raise errors.SystemFailed(f"pdf-inspector failed: {out.stderr.strip()}", status=None)
    return contract.Call(json.loads(out.stdout) | {"version": installed}, cost=contract.Cost(usd=0.0))


_VERSION: list[str] = []
_VERSION_LOCK = threading.Lock()


def version(deadline: budget.Budget) -> str:
    """Look up the installed version once, bounded by this page's remaining time."""
    if _VERSION:
        return _VERSION[0]
    if not _VERSION_LOCK.acquire(timeout=max(0.0, deadline.remaining())):
        raise errors.SystemTimeout(f"pdf-inspector version lookup ran past the call's {deadline.total:g} s")
    try:
        if not _VERSION:
            script = "from importlib.metadata import version; print(version('pdf-inspector'))"
            out = run_python(script, [], deadline, "version lookup")
            if out.returncode:
                raise FileNotFoundError("pdf-inspector isn't installed or importable: "
                                        "pip install 'omni-parse-bench[pdf-inspector]'")
            _VERSION.append(out.stdout.strip())
        return _VERSION[0]
    finally:
        _VERSION_LOCK.release()


def run_python(script: str, args: list[str], deadline: budget.Budget,
               stage: str) -> subprocess.CompletedProcess:
    """Run a Python child within the page deadline; kill its process group when it times out."""
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
        raise errors.SystemTimeout(f"pdf-inspector {stage} ran past the call's {deadline.total:g} s") from exc
    return subprocess.CompletedProcess(command, proc.returncode, stdout, stderr)


def as_pdf(page: Path, dest: Path, *, dpi: float = DPI) -> None:
    """Wrap an image in a one-page PDF losslessly at `dpi`, preserving its pixel dimensions and alpha."""
    if page.suffix.lower() != ".pdf":
        import img2pdf
        import io
        from PIL import Image

        layout = img2pdf.get_fixed_dpi_layout_fun((dpi, dpi))
        with Image.open(page) as image:
            image.load()
            png = io.BytesIO()
            image.save(png, format="PNG")
        dest.write_bytes(img2pdf.convert(png.getvalue(), layout_fun=layout))
    else:
        dest.write_bytes(page.read_bytes())


def parse(raw: dict, request: contract.Request, config: PdfInspector | None = None) -> tuple[dict, dict]:
    """The Markdown as html; a page the package returns no Markdown for is an empty page."""
    with adapter.reading("pdf-inspector's markdown"):
        md = raw["markdown"] or ""
        return {o: markdown.to_html(md) if md.strip() else "" for o in request.outputs}, {}
