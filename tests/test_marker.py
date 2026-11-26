"""Marker's adapters: its saved answer read, its labels, its modes. No test imports `marker` except the one
that checks LABELS against the installed package's block types, which is skipped without it."""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from omni_parse_bench import harness, views  # noqa: E402
from omni_parse_bench.harness import contract, errors  # noqa: E402
from omni_parse_bench.harness.providers import marker_pdf  # noqa: E402

FIXTURE = Path(__file__).parent / "fixtures" / "marker" / "forms_page_fast.json"
BOTH = frozenset({"html", "blocks"})


@pytest.fixture(autouse=True)
def close_marker_worker():
    yield
    marker_pdf.close()


def _node(kind, bbox, html, children=None, id_="/page/0/x/0"):
    node = {"id": id_, "block_type": kind, "bbox": bbox, "html": html}
    return node | ({"children": children} if children else {})


def _page(*children):
    return _node("Page", [0, 0, 200, 100], "", list(children), id_="/page/0/Page/0")


def _raw(html, pages):
    return {"html": html, "json": {"block_type": "Document", "children": pages, "metadata": {}}}


def test_the_two_rows_are_two_systems_each_with_its_own_mode():
    assert harness.ADAPTERS["marker"].MODE == "balanced" and harness.ADAPTERS["marker-fast"].MODE == "fast"
    (r,) = harness.system("marker-fast").requests(BOTH)
    assert r.sent["mode"] == "fast" and r.sent["package"] == "marker-pdf==2.2.0"
    assert r.sent["settings"] == {"keep_pageheader_in_output": True, "keep_pagefooter_in_output": True}
    assert harness.system("marker").requests(frozenset({"html"}))[0].sent["mode"] == "balanced"


def test_a_saved_answer_is_read_as_html_and_labelled_blocks():
    fx = json.loads(FIXTURE.read_text())
    api = harness.system(fx["provider"], fx["options"])
    outs, errs = api.parse(fx["raw"], contract.Request(BOTH, fx["sent"]))
    assert errs == {} and outs["html"] == fx["raw"]["html"]
    blocks = outs["blocks"]
    assert blocks and all(b["label"] in views.LABELS for b in blocks)
    assert {b["label"] for b in blocks} >= {"heading", "text", "form", "list", "page_furniture", "table"}
    assert all(0 <= v <= 1 for b in blocks for v in b["bbox"])
    assert all(b["text"] for b in blocks)


def test_blocks_are_the_page_boxes_divided_by_its_size_and_a_groups_parts():
    cap = _node("Caption", [20, 50, 60, 60], "<p>Fig 1</p>")
    pic = _node("Picture", [20, 10, 60, 50], "")
    group = _node("FigureGroup", [20, 10, 60, 60], "<content-ref src='a'></content-ref>", [pic, cap])
    items = [_node("ListItem", [0, 0, 1, 1], "<li>one</li>", id_="i1")]
    lst = _node("ListGroup", [100, 0, 200, 100], "<ul><content-ref src='i1'></content-ref></ul>", items)
    outs, errs = marker_pdf.parse(_raw("<p/>", [_page(group, lst)]), contract.Request(BOTH, {}))
    assert errs == {}
    assert [(b["label"], b["bbox"], b["text"]) for b in outs["blocks"]] == [
        ("figure", [0.1, 0.1, 0.3, 0.5], ""), ("caption", [0.1, 0.5, 0.3, 0.6], "Fig 1"),
        ("list", [0.5, 0.0, 1.0, 1.0], "one")]


def test_a_block_type_the_table_lacks_fails_the_blocks_only():
    odd = _node("Span", [0, 0, 1, 1], "x")
    outs, errs = marker_pdf.parse(_raw("<p>a</p>", [_page(odd)]), contract.Request(BOTH, {}))
    assert outs == {"html": "<p>a</p>"} and "Span" in errs["blocks"]


def test_every_label_is_a_view_label_and_every_marker_block_type_is_decided():
    assert set(marker_pdf.LABELS.values()) <= set(views.LABELS)
    schema = pytest.importorskip("marker.schema")
    undecided = {t.name for t in schema.BlockTypes} - set(marker_pdf.LABELS) - marker_pdf.GROUPS
    assert undecided == {"Line", "Span", "Char", "TableCell", "Page", "Document"}


def test_a_failure_of_marker_is_the_pages_failure(monkeypatch, tmp_path):
    fake_marker(tmp_path, monkeypatch)
    monkeypatch.setenv("MARKER_FAKE_MODE", "error")
    page = tmp_path / "p.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)
    with pytest.raises(errors.SystemFailed, match="bad page"):
        marker_pdf.call(page, request, config=config)


FAKE_MARKER = {
    "surya/__init__.py": "",
    "surya/settings.py": "class Settings: SURYA_INFERENCE_KEEP_ALIVE = True\nsettings = Settings()\n",
    "surya/inference/__init__.py": "",
    "surya/inference/backends/__init__.py": "",
    "surya/inference/backends/spawn.py": "def _write_sentinel(backend, data): pass\n",
    "marker/__init__.py": "",
    "marker/converters/__init__.py": "",
    "marker/converters/pdf.py": '''
import os, subprocess, sys, time
from pathlib import Path
from types import SimpleNamespace
class PdfConverter:
    def __init__(self, artifact_dict, config): self.config = config
    def build_document(self, path):
        if os.environ.get("MARKER_FAKE_MODE") == "spawn":
            pid_file = os.environ["MARKER_CHILD_PID"]
            code = ("import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                    "open(" + repr(pid_file) + ", 'w').write(str(os.getpid())); "
                    "time.sleep(120)")
            subprocess.Popen([sys.executable, "-c", code])
            time.sleep(120)
        if os.environ.get("MARKER_FAKE_MODE") == "hold-lock":
            started = Path(os.environ["MARKER_SLOW_STARTED"])
            started.touch()
            release = Path(os.environ["MARKER_SLOW_RELEASE"])
            while not release.exists(): time.sleep(0.05)
        if os.environ.get("MARKER_FAKE_MODE") == "error": raise RuntimeError("bad page")
        return SimpleNamespace(image=Path(path).read_bytes())
''',
    "marker/renderers/__init__.py": "",
    "marker/renderers/html.py": '''
from types import SimpleNamespace
class HTMLRenderer:
    def __init__(self, settings): pass
    def __call__(self, document): return SimpleNamespace(html=document.image.hex())
''',
    "marker/renderers/json.py": '''
from types import SimpleNamespace
class Node:
    def __init__(self, id, block_type, bbox, html, children=None):
        self.id, self.block_type, self.bbox, self.html = id, block_type, bbox, html
        self.children = children or []
    def model_dump(self, mode="json"):
        return {"id": self.id, "block_type": self.block_type, "bbox": self.bbox, "html": self.html,
                "polygon": [[0, 0], [200, 0], [200, 100]], "images": {"vendor": "retained"},
                "section_hierarchy": {1: "page"},
                "children": [c.model_dump(mode=mode) for c in self.children] or None}
class JSONRenderer:
    def __init__(self, settings): pass
    def __call__(self, document):
        page = Node("page", "Page", [0, 0, 200, 100], "")
        return SimpleNamespace(model_dump=lambda mode="json": {
            "block_type": "Document", "metadata": {"full_vendor_json": True},
            "children": [page.model_dump(mode=mode)]})
''',
    "marker/models/__init__.py": '''
import os
from pathlib import Path
def create_model_dict():
    if os.environ.get("MARKER_FAKE_MODELS_MISSING"):
        raise FileNotFoundError("model weights missing")
    if os.environ.get("MARKER_MODEL_LOADS"):
        with Path(os.environ["MARKER_MODEL_LOADS"]).open("a") as f: f.write("x")
    if os.environ.get("MARKER_FAKE_SERVER_PID"):
        pid_file = os.environ["MARKER_FAKE_SERVER_PID"]
        code = ("import os,signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "open(" + repr(pid_file) + ", 'w').write(str(os.getpid())); time.sleep(120)")
        import subprocess, sys
        server = subprocess.Popen([sys.executable, "-c", code], start_new_session=True)
        from surya.inference.backends import spawn
        spawn._write_sentinel("fake", {"pid": server.pid, "cleanup_id": str(server.pid),
                                        "cleanup_kind": "process"})
    return {}
''',
}


def fake_marker(tmp_path, monkeypatch):
    root = tmp_path / "fake-site"
    for name, content in FAKE_MARKER.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    metadata = root / "marker_pdf-2.2.0.dist-info"
    metadata.mkdir()
    (metadata / "METADATA").write_text("Name: marker-pdf\nVersion: 2.2.0\n")
    pythonpath = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(root), pythonpath])))
    return root


def wait_for_file(path, future, timeout=15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if future.done():
            future.result()
        if time.monotonic() >= deadline:
            pytest.fail(f"worker did not create {path} within {timeout}s")
        time.sleep(0.05)


def test_faked_child_runs_fast_mode_and_preserves_image_bytes(tmp_path, monkeypatch):
    fake_marker(tmp_path, monkeypatch)
    image = tmp_path / "page.png"
    image_bytes = b"\x89PNG\r\n\x1a\nraw image bytes"
    image.write_bytes(image_bytes)
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)

    result = marker_pdf.call(image, request, timeout=15, config=config)
    assert result.raw["html"] == image_bytes.hex()
    assert result.raw["mode"] == "fast" and result.raw["version"] == "2.2.0"
    assert result.raw["json"]["metadata"]["full_vendor_json"] is True
    assert result.raw["json"]["children"][0]["images"] == {"vendor": "retained"}
    outs, errs = config.parse(result.raw, request)
    assert errs == {} and outs["blocks"] == []


def test_mode_worker_reuses_loaded_models_across_pages(tmp_path, monkeypatch):
    fake_marker(tmp_path, monkeypatch)
    loads = tmp_path / "model-loads"
    monkeypatch.setenv("MARKER_MODEL_LOADS", str(loads))
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)
    for index in range(2):
        page = tmp_path / f"page-{index}.pdf"
        page.write_bytes(f"page {index}".encode())
        marker_pdf.call(page, request, timeout=15, config=config)
    assert loads.read_text() == "x"


def test_waiting_for_mode_lock_obeys_page_budget(tmp_path, monkeypatch):
    fake_marker(tmp_path, monkeypatch)
    started, release = tmp_path / "started", tmp_path / "release"
    monkeypatch.setenv("MARKER_FAKE_MODE", "hold-lock")
    monkeypatch.setenv("MARKER_SLOW_STARTED", str(started))
    monkeypatch.setenv("MARKER_SLOW_RELEASE", str(release))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)

    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(marker_pdf.call, page, request, timeout=15, config=config)
        wait_for_file(started, first)
        with pytest.raises(errors.SystemTimeout, match="waiting for its worker"):
            marker_pdf.call(page, request, timeout=0.2, config=config)
        assert not first.done()
        release.touch()
        first.result(timeout=10)


def test_stalled_worker_input_reader_obeys_page_budget(tmp_path):
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], stdin=subprocess.PIPE,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True,
                            start_new_session=True)
    mode, tracker = config.MODE, tmp_path / "servers.jsonl"
    tracker.touch()
    output = queue.Queue()
    marker_pdf._WORKERS[mode], marker_pdf._OUTPUTS[mode], marker_pdf._TRACKERS[mode] = proc, output, tracker
    threading.Thread(target=marker_pdf._read_output, args=(proc, output), daemon=True).start()

    with pytest.raises(errors.SystemTimeout):
        marker_pdf.call(Path("p" + "x" * 1_000_000), request, timeout=0.5, config=config)
    assert proc.poll() is not None


def test_missing_marker_package_has_an_install_hint(tmp_path, monkeypatch):
    root = tmp_path / "empty-site"
    root.mkdir()
    (root / "sitecustomize.py").write_text('''
import importlib.metadata
original = importlib.metadata.version
def version(name):
    if name == "marker-pdf": raise importlib.metadata.PackageNotFoundError(name)
    return original(name)
importlib.metadata.version = version
''')
    monkeypatch.setenv("PYTHONPATH", str(root))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)
    with pytest.raises(FileNotFoundError, match="uv pip install marker-pdf==2.2.0"):
        marker_pdf.call(page, request, timeout=10, config=config)


def test_missing_marker_weights_have_an_actionable_hint(tmp_path, monkeypatch):
    fake_marker(tmp_path, monkeypatch)
    monkeypatch.setenv("MARKER_FAKE_MODELS_MISSING", "1")
    page = tmp_path / "page.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)
    with pytest.raises(FileNotFoundError, match="Hugging Face cache"):
        marker_pdf.call(page, request, timeout=10, config=config)


def test_cold_version_lookup_is_bounded_after_it_starts(tmp_path, monkeypatch):
    root = tmp_path / "slow-site"
    root.mkdir()
    started = tmp_path / "version-lookup-started"
    (root / "sitecustomize.py").write_text('''
import importlib.metadata, os, pathlib, time
original = importlib.metadata.version
def version(name):
    if name == "marker-pdf":
        pathlib.Path(os.environ["MARKER_VERSION_STARTED"]).touch()
        time.sleep(120)
    return original(name)
importlib.metadata.version = version
''')
    monkeypatch.setenv("PYTHONPATH", str(root))
    monkeypatch.setenv("MARKER_VERSION_STARTED", str(started))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(marker_pdf.call, page, request, timeout=20, config=config)
        wait_for_file(started, future)
        with pytest.raises(errors.SystemTimeout):
            future.result(timeout=25)


def test_timeout_kills_marker_descendant_by_pid(tmp_path, monkeypatch):
    fake_marker(tmp_path, monkeypatch)
    monkeypatch.setenv("MARKER_FAKE_MODE", "spawn")
    child_pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("MARKER_CHILD_PID", str(child_pid_file))
    server_pid_file = tmp_path / "server.pid"
    monkeypatch.setenv("MARKER_FAKE_SERVER_PID", str(server_pid_file))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"pdf")
    config = harness.system("marker-fast")
    (request,) = config.requests(BOTH)

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(marker_pdf.call, page, request, timeout=20, config=config)
        wait_for_file(server_pid_file, future)
        wait_for_file(child_pid_file, future)
        child_pid = int(child_pid_file.read_text())
        server_pid = int(server_pid_file.read_text())
        with pytest.raises(errors.SystemTimeout):
            future.result(timeout=25)

    for pid in (child_pid, server_pid):
        deadline = time.monotonic() + 5
        while True:
            try:
                os.kill(pid, 0)
            except ProcessLookupError:
                break
            if time.monotonic() >= deadline:
                pytest.fail(f"Marker descendant {pid} survived process-group termination")
            time.sleep(0.05)
