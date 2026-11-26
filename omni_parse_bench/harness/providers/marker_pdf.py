"""Marker (datalab-to/marker), the `marker-pdf` package run in a persistent child: fast and balanced modes."""
from __future__ import annotations

import dataclasses
import atexit
import json
import os
import queue
import re
import signal
import subprocess
import sys
import threading
import tempfile
import time
from pathlib import Path
from typing import Any, ClassVar

from bs4 import BeautifulSoup
from omni_bench_core import adapter

from .. import budget, contract, errors, layout
from ..adapter import Parser

SUPPORTS = frozenset({"html", "blocks"})
PACKAGE = "marker-pdf==2.2.0"
# Marker's block types (marker.schema.BlockTypes, as its JSON output names them) onto views.LABELS. Left
# out on purpose, so a page that has one fails its blocks with the type named: Line, Span, Char (text inside
# a block, never a region), TableCell (inside its Table), Page and Document (the frame). A group is not a
# region of its own: its parts are (GROUPS).
LABELS = {
    "Text": "text", "TextInlineMath": "text", "TableOfContents": "text", "Reference": "text",
    "Handwriting": "text", "Bibliography": "text", "SectionHeader": "heading", "PageHeader": "page_furniture",
    "PageFooter": "page_furniture", "ListGroup": "list", "ListItem": "list", "Caption": "caption",
    "Footnote": "footnote", "Equation": "equation", "Code": "code", "Table": "table", "Form": "form",
    "Picture": "figure", "Figure": "figure", "Diagram": "figure", "ChemicalBlock": "figure",
    "ComplexRegion": "figure",
}
# A group holds a figure or table with its caption; the parts are the regions.
GROUPS = frozenset({"FigureGroup", "TableGroup", "PictureGroup"})
# Marker's placeholder for a child block inside its parent's html (marker.renderers.CONTENT_REF_RE).
CONTENT_REF = re.compile(r"<content-ref src='([^']*)'></content-ref>")
_WORKERS: dict[str, subprocess.Popen] = {}
_OUTPUTS: dict[str, queue.Queue] = {}
_TRACKERS: dict[str, Path] = {}
_LOCKS = {"fast": threading.Lock(), "balanced": threading.Lock()}
_WORKERS_LOCK = threading.Lock()


@dataclasses.dataclass(frozen=True)
class Marker(Parser):
    """Marker's `balanced` mode, the one its README names the default on a GPU ("`--mode balanced`
    (GPU default)"): `marker-pdf` 2.2.0 in a persistent child process, html and layout blocks.

    License: the code is Apache-2.0; the model weights (Surya, Indra) are under Datalab's modified AI Pubs
    Open RAIL-M (free for research, personal use and startups under $5M in funding or revenue).

    Marker has two modes the README gives numbers for that need no key, and this adapter runs each as a row
    of its own, the mode being the class's, not an option, so a run is never filed under a mode it did not
    use: `marker-fast` ("Marker (fast)", `--mode fast`, CPU, one in-process ONNX stack) and `marker`
    ("Marker", `--mode balanced`: smart routing, pdftext and Indra layout on clean prose pages, and the
    Surya 2.5 VLM on tables, math, CJK and scripts it does not read, and scans). The README's other two
    modes, `vllm` (full-page VLM on every page) and `no_ocr`, and its `--use_llm` hybrid (an LLM, Gemini
    `gemini-3.5-flash` by default, run over the result: needs GEMINI_API_KEY or another configured service)
    are not rows. `balanced` needs the Surya inference server: Marker starts it itself on first use (vLLM in
    Docker on an NVIDIA GPU, llama.cpp elsewhere), or reaches one already running at `SURYA_INFERENCE_URL`
    (http://host:port/v1), which is how a run points it at a server of ours.

    How a page is processed:

      1. Input loading        opb sends the one-page PDF or image file; Marker's
                              `PdfConverter.build_document` reads it.
      2. Image preprocessing  Marker's own: the page rendered by its pdf provider.
      3. Model inference      per the mode above (the layout model, reading order, line OCR or the VLM).
      4. Vendor output parsing  the document's blocks, rendered twice, as Marker's own html (`HTMLRenderer`)
                              and its JSON block tree (`JSONRenderer`): each block's type, box in the
                              page's pixels and html.
      5. Mapping to opb outputs  html is Marker's html as it is; blocks are each block's type (LABELS) with
                              its box divided by the page's size and its html as text. A group (figure or
                              table with its caption) gives its parts.

    Differences from the vendor:

      - page headers and footers are kept (`keep_pageheader_in_output`, `keep_pagefooter_in_output`: the
        README's `--keep_headers_footers`; Marker drops them by default), as every other adapter keeps them.

    One persistent child per mode keeps Marker and its models loaded across pages; each page's conversion
    has its own Budget. A timeout stops the child and its Surya server, if it started one. The package isn't
    one of this package's dependencies (it brings PyTorch):

        uv pip install marker-pdf==2.2.0
        opb init marker-fast > config.yaml
        opb run --config config.yaml --set rows.sample=20
    """

    MODE: ClassVar[str] = "balanced"
    name: ClassVar[str] = "marker"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = ("SURYA_INFERENCE_URL, the address of a running Surya server, for `balanced`; "
                          "else Marker starts one")
    workers: ClassVar[int] = 1

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


@dataclasses.dataclass(frozen=True)
class MarkerFast(Marker):
    """Marker's `fast` mode, "Marker (fast)": `marker-pdf` 2.2.0 with `--mode fast`, the README's CPU/MPS
    default: Indra ONNX layout, reading order and line OCR (about 18 MB of weights), no VLM server
    and no LLM. The README gives it 71.0 on OmniParseBench at 23.6 pages/s. Licenses, steps and differences
    are Marker's (`Marker`).

        opb init marker-fast > config.yaml
        opb run --config config.yaml --set rows.sample=20
    """

    MODE: ClassVar[str] = "fast"
    name: ClassVar[str] = "marker-fast"
    ENV: ClassVar[str] = ""


def requests(wants: frozenset[str], config: Marker) -> list[contract.Request]:
    """One call answers both outputs."""
    sent = {"package": PACKAGE, "mode": config.MODE,
            "settings": {"keep_pageheader_in_output": True, "keep_pagefooter_in_output": True}}
    return [contract.Request(wants & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Marker) -> contract.Call:
    """Reuse a mode's child for its models, with each page bounded by its own budget."""
    deadline = budget.Budget(timeout)
    mode = config.MODE
    lock = _LOCKS[mode]
    if not lock.acquire(timeout=deadline.remaining()):
        raise errors.SystemTimeout(
            f"marker ({mode}) ran past the call's {deadline.total:g} s waiting for its worker"
        )
    try:
        proc, output = _worker(mode)
        try:
            wrote = _write_request(proc, json.dumps({"page": str(page), "sent": request.sent}) + "\n",
                                   deadline.remaining())
        except errors.SystemFailed:
            _stop_worker(mode, expected=proc)
            raise
        if not wrote:
            _stop_worker(mode, expected=proc)
            raise errors.SystemTimeout(
                f"marker ({mode}) ran past the call's {deadline.total:g} s"
            )
        try:
            result = output.get(timeout=deadline.remaining())
        except queue.Empty as exc:
            _stop_worker(mode, expected=proc)
            raise errors.SystemTimeout(
                f"marker ({mode}) ran past the call's {deadline.total:g} s"
            ) from exc
        if result is None:
            _stop_worker(mode, expected=proc)
            raise errors.SystemFailed(f"marker ({mode}) worker exited before returning a page", status=None)
    finally:
        lock.release()
    if "setup_error" in result:
        raise FileNotFoundError("marker-pdf isn't installed: uv pip install marker-pdf==2.2.0")
    if "model_error" in result:
        raise FileNotFoundError(result["model_error"])
    if "version_error" in result:
        raise RuntimeError(
            f"marker-pdf {result['version_error']} is installed; this adapter is for {PACKAGE}"
        )
    if "error" in result:
        raise errors.SystemFailed(f"marker ({mode}) failed on the page: {result['error']}", status=None)
    return contract.Call(result, cost=contract.Cost(usd=0.0))


def _write_request(proc: subprocess.Popen, line: str, timeout: float) -> bool:
    """Write and flush in a daemon thread: a pipe blocked by a stuck reader cannot outlive the page budget."""
    done = threading.Event()
    failure: list[BaseException] = []

    def write() -> None:
        try:
            proc.stdin.write(line)
            proc.stdin.flush()
        except BaseException as exc:
            failure.append(exc)
        finally:
            done.set()

    threading.Thread(target=write, daemon=True).start()
    if not done.wait(timeout):
        return False
    if failure:
        raise errors.SystemFailed(
            f"marker worker input pipe failed: {failure[0]}", status=None
        ) from failure[0]
    return True


def _worker(mode: str) -> tuple[subprocess.Popen, queue.Queue]:
    with _WORKERS_LOCK:
        proc = _WORKERS.get(mode)
        if proc is None or proc.poll() is not None:
            tracker_fd, tracker_name = tempfile.mkstemp(prefix=f"opb-marker-{mode}-", suffix=".jsonl")
            os.close(tracker_fd)
            tracker = Path(tracker_name)
            env = os.environ.copy()
            env["MARKER_SERVER_TRACKER"] = str(tracker)
            proc = subprocess.Popen([sys.executable, "-u", "-c", _WORKER], stdin=subprocess.PIPE,
                                    stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                                    errors="replace", bufsize=1, start_new_session=True, env=env)
            output: queue.Queue = queue.Queue()
            threading.Thread(target=_read_output, args=(proc, output), daemon=True).start()
            _WORKERS[mode], _OUTPUTS[mode], _TRACKERS[mode] = proc, output, tracker
        return proc, _OUTPUTS[mode]


def _read_output(proc: subprocess.Popen, output: queue.Queue) -> None:
    for line in proc.stdout:
        try:
            output.put(json.loads(line))
        except json.JSONDecodeError:
            output.put({"error": f"worker returned invalid JSON: {line[:200]}"})
    output.put(None)


def _stop_worker(mode: str, *, expected: subprocess.Popen | None = None) -> None:
    with _WORKERS_LOCK:
        current = _WORKERS.get(mode)
        if expected is not None and current is not expected:
            return
        proc = _WORKERS.pop(mode, None)
        _OUTPUTS.pop(mode, None)
        tracker = _TRACKERS.pop(mode, None)
    if proc is None:
        return
    _terminate_worker(proc, tracker)


def _terminate_worker(proc: subprocess.Popen, tracker: Path | None) -> None:
    """Give the whole worker group a TERM grace, then kill it and all detached servers it recorded."""
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    grace_end = time.monotonic() + 5
    while time.monotonic() < grace_end:
        proc.poll()  # reap a worker that exited promptly so only surviving group members extend the grace
        try:
            os.killpg(proc.pid, 0)
        except ProcessLookupError:
            break
        except PermissionError:
            # macOS may report an existing process group as inaccessible; keep the TERM grace.
            pass
        time.sleep(min(0.05, max(0, grace_end - time.monotonic())))
    try:
        # Do this even if the worker exited: TERM-ignoring children can remain in its group.
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    if proc.poll() is None:
        proc.wait()
    _kill_tracked_servers(tracker)


def _kill_tracked_servers(tracker: Path | None) -> None:
    if tracker is None:
        return
    try:
        entries = [json.loads(line) for line in tracker.read_text().splitlines() if line.strip()]
    except (FileNotFoundError, json.JSONDecodeError):
        entries = []
    for entry in entries:
        if entry.get("kind") == "process" and isinstance(entry.get("pid"), int):
            try:
                os.killpg(entry["pid"], signal.SIGKILL)
            except ProcessLookupError:
                pass
        elif entry.get("kind") == "docker" and entry.get("cleanup_id"):
            try:
                subprocess.run(["docker", "kill", str(entry["cleanup_id"])], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
            except (FileNotFoundError, subprocess.TimeoutExpired):
                pass
    tracker.unlink(missing_ok=True)


@atexit.register
def close() -> None:
    for mode in tuple(_WORKERS):
        _stop_worker(mode)


_WORKER = r'''import contextlib, importlib.metadata, json, os, signal, sys

class ModelLoadError(Exception): pass
def _terminate(signum, frame):
    raise SystemExit(128 + signum)
signal.signal(signal.SIGTERM, _terminate)
tracker = os.environ.get("MARKER_SERVER_TRACKER")
def _record_server(entry):
    if tracker:
        with open(tracker, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
            f.flush()
initialized = False
while True:
    line = sys.stdin.readline()
    if not line: break
    try:
        job = json.loads(line)
        sent = job["sent"]
        with contextlib.redirect_stdout(sys.stderr):
            if not initialized:
                installed = importlib.metadata.version("marker-pdf")
                if installed != "2.2.0":
                    raise RuntimeError("VERSION:" + installed)
                from marker.converters.pdf import PdfConverter
                from marker.renderers.html import HTMLRenderer
                from marker.renderers.json import JSONRenderer
                from marker.models import create_model_dict
                from surya.settings import settings as surya_settings
                try:
                    from surya.inference.backends import spawn as surya_spawn
                    _write_sentinel = surya_spawn._write_sentinel
                    def _tracked_sentinel(backend, data):
                        _write_sentinel(backend, data)
                        if data.get("cleanup_kind") == "process":
                            _record_server({"kind": "process", "pid": data.get("pid"),
                                            "backend": backend, "cleanup_id": data.get("cleanup_id")})
                        elif data.get("cleanup_kind") == "docker":
                            _record_server({"kind": "docker", "cleanup_id": data.get("cleanup_id"),
                                            "backend": backend})
                    surya_spawn._write_sentinel = _tracked_sentinel
                except ImportError:
                    pass
                surya_settings.SURYA_INFERENCE_KEEP_ALIVE = False
                try: models = create_model_dict()
                except Exception as exc:
                    raise ModelLoadError(
                        f"could not load Marker {sent['mode']} model weights: "
                        f"{type(exc).__name__}: {exc}. Check model access and the Hugging Face cache; "
                        "balanced mode also needs the Surya VLM weights or a configured SURYA_INFERENCE_URL."
                    ) from exc
                settings = sent["settings"]
                converter = PdfConverter(artifact_dict=models, config={"mode": sent["mode"], **settings})
                html_renderer, json_renderer = HTMLRenderer(settings), JSONRenderer(settings)
                initialized = True
            document = converter.build_document(job["page"])
            html = html_renderer(document).html
            tree = json_renderer(document)
            raw = {"html": html, "json": tree.model_dump(mode="json"),
                   "mode": sent["mode"], "version": installed}
        result = raw
    except RuntimeError as exc:
        if str(exc).startswith("VERSION:"):
            result = {"version_error": str(exc).removeprefix("VERSION:")}
        else:
            result = {"error": f"{type(exc).__name__}: {exc}"}
    except ModelLoadError as exc:
        result = {"model_error": str(exc)}
    except (ModuleNotFoundError, importlib.metadata.PackageNotFoundError) as exc:
        result = {"setup_error": str(exc)}
    except Exception as exc:
        result = {"error": f"{type(exc).__name__}: {exc}"}
    print(json.dumps(result), flush=True)'''


def parse(raw: dict, request: contract.Request, config: Marker | None = None) -> tuple[dict, dict]:
    """Marker's html as it is, and its blocks on the page, in Marker's reading order."""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = raw["html"]
    if "blocks" in request.outputs:
        try:
            with adapter.reading("Marker's JSON block tree"):
                outputs["blocks"] = [b for page in raw["json"]["children"] for b in blocks(page)]
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs


def blocks(page: dict) -> list[dict]:
    """The labeled blocks of one page of the tree, boxes divided by the page's own box."""
    x0, y0, x1, y1 = page["bbox"]
    frame = (x1 - x0, y1 - y0)
    out = []

    def walk(node: dict) -> None:
        kind = node["block_type"]
        if kind in GROUPS:
            for child in node.get("children") or []: walk(child)
            return
        label = layout.label(LABELS, kind)
        box = [node["bbox"][0] - x0, node["bbox"][1] - y0, node["bbox"][2] - x0, node["bbox"][3] - y0]
        out.append(layout.block(label, box, frame, text(node)))

    for child in page.get("children") or []: walk(child)
    return out


def text(node: dict) -> str:
    """A block's text: its html with its children's put in place, as plain text."""
    def html(n: dict) -> str:
        parts = {c["id"]: html(c) for c in n.get("children") or []}
        return CONTENT_REF.sub(lambda m: parts.get(m[1], ""), n["html"])
    return " ".join(BeautifulSoup(html(node), "html.parser").get_text(" ").split())
