"""OpenDataLoader: its JSON elements as blocks and its html as html, from a recorded answer (no Java)."""
from __future__ import annotations

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

pytest.importorskip("httpx")
pytest.importorskip("pypdfium2")

from omni_parse_bench.harness import errors  # noqa: E402
from omni_parse_bench.harness.providers import opendataloader as odl  # noqa: E402

# A page of 200 x 100 points, as the engine writes its elements (boxes: left, bottom, right, top).
ANSWER = {
    "size": [200.0, 100.0], "version": "2.5.24",
    "html": "<!DOCTYPE html>\n<html><head><title>page.pdf</title></head>\n<body>\n<h1>Title</h1>\n\n"
            "<p>alpha beta</p>\n</body></html>\n",
    "json": {"kids": [
        {"type": "heading", "id": 1, "page number": 1, "bounding box": [20, 80, 100, 90], "content": "Title",
         "heading level": 1},
        {"type": "paragraph", "id": 2, "page number": 1, "bounding box": [20, 60, 180, 70],
         "content": "alpha  beta"},
        {"type": "text block", "id": 3, "page number": 1, "bounding box": [20, 40, 180, 58], "kids": [
            {"type": "paragraph", "id": 4, "page number": 1, "bounding box": [20, 50, 180, 58],
             "content": "one"},
            {"type": "caption", "id": 5, "page number": 1, "bounding box": [20, 40, 180, 48],
             "content": "Fig 1"}]},
        {"type": "list", "id": 6, "page number": 1, "bounding box": [20, 20, 100, 38], "list items": [
            {"type": "list item", "content": "a", "kids": []},
            {"type": "list item", "content": "b", "kids": [
                {"type": "paragraph", "content": "more"}]}]},
        {"type": "table", "id": 7, "page number": 1, "bounding box": [110, 10, 190, 38], "rows": [
            {"type": "table row", "cells": [
                {"type": "table cell", "kids": [{"type": "paragraph", "content": "x"}]},
                {"type": "table cell", "kids": [{"type": "paragraph", "content": "1"}]}]}]},
        {"type": "image", "id": 8, "page number": 1, "bounding box": [0, 0, 20, 10]},
        {"type": "footer", "id": 9, "page number": 1, "bounding box": [80, 0, 120, 8],
         "kids": [{"type": "paragraph", "content": "page 3"}]},
        {"type": "form field", "id": 10, "page number": 1, "bounding box": [130, 90, 150, 98],
         "content": "agree", "field role": "check box", "checked": "on"},
    ]},
}


def test_it_asks_one_call_for_both_outputs_with_headers_kept():
    (r,) = odl.OpenDataLoader().requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["blocks", "html"]
    assert r.sent["include_header_footer"] is True and r.sent["image_output"] == "off"
    assert r.sent["package"] == odl.PACKAGE
    (off,) = odl.OpenDataLoader(furniture=False).requests(frozenset({"html"}))
    assert off.sent["include_header_footer"] is False


def test_html_is_the_engines_body_as_it_is():
    (r,) = odl.OpenDataLoader().requests(frozenset({"html"}))
    outs, errs = odl.parse(ANSWER, r)
    assert errs == {} and outs == {"html": "<h1>Title</h1>\n\n<p>alpha beta</p>"}


def test_blocks_are_labelled_flipped_to_the_top_left_and_scaled():
    (r,) = odl.OpenDataLoader().requests(frozenset({"blocks"}))
    outs, errs = odl.parse(ANSWER, r)
    assert errs == {}
    got = [(b["label"], b["text"]) for b in outs["blocks"]]
    assert got == [("heading", "Title"), ("text", "alpha beta"), ("text", "one"), ("caption", "Fig 1"),
                   ("list", "a b more"), ("table", "x 1"), ("figure", ""), ("page_furniture", "page 3"),
                   ("form", "agree")]
    assert outs["blocks"][0]["bbox"] == [0.1, 0.1, 0.5, 0.2]
    assert outs["blocks"][6]["bbox"] == [0.0, 0.9, 0.1, 1.0]


def test_an_element_type_not_in_the_table_fails_only_the_blocks():
    (r,) = odl.OpenDataLoader().requests(frozenset({"html", "blocks"}))
    answer = json.loads(json.dumps(ANSWER))
    answer["json"]["kids"].append({"type": "mystery", "bounding box": [0, 0, 1, 1]})
    outs, errs = odl.parse(answer, r)
    assert "blocks" not in outs and "mystery" in errs["blocks"] and "html" in outs


def test_every_label_is_one_of_the_benchmarks():
    from omni_parse_bench import views

    assert set(odl.LABELS.values()) <= set(views.LABELS)


def test_a_page_with_nothing_on_it_is_an_empty_page_not_a_failure():
    (r,) = odl.OpenDataLoader().requests(frozenset({"html", "blocks"}))
    empty = {"size": [10, 10], "html": "<html><body>\n</body></html>", "json": {"kids": []}}
    outs, errs = odl.parse(empty, r)
    assert errs == {} and outs == {"html": "", "blocks": []}


def _child_env(monkeypatch, tmp_path):
    import os

    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + (os.pathsep + inherited if inherited else ""))
    dist = tmp_path / "opendataloader_pdf-2.5.24.dist-info"
    dist.mkdir(exist_ok=True)
    (dist / "METADATA").write_text("Metadata-Version: 2.1\nName: opendataloader-pdf\nVersion: 2.5.24\n")


def _fake_vendor(tmp_path, source: str):
    (tmp_path / "opendataloader_pdf.py").write_text(source)


def _blank_pdf(path):
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument.new()
    try:
        doc.new_page(200, 100)
        doc.save(path)
    finally:
        doc.close()


@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA"])
def test_production_child_passes_lossless_image_pdf_to_vendor(mode, tmp_path, monkeypatch):
    import base64
    from PIL import Image

    _child_env(monkeypatch, tmp_path)
    _fake_vendor(tmp_path, '''
import base64, json, pikepdf
from pathlib import Path
def convert(input_path, output_dir, **kwargs):
    with pikepdf.Pdf.open(input_path) as pdf:
        page = pdf.pages[0]
        xobj = next(iter(page.Resources.XObject.values()))
        color = xobj.read_bytes()
        alpha = xobj.SMask.read_bytes() if "/SMask" in xobj else b""
        box = page.MediaBox
        value = {"width": int(xobj.Width), "height": int(xobj.Height),
                 "color": base64.b64encode(color).decode(), "alpha": base64.b64encode(alpha).decode(),
                 "page_width": float(box[2])-float(box[0]), "page_height": float(box[3])-float(box[1])}
    out = Path(output_dir); out.mkdir(parents=True)
    (out / "page.json").write_text(json.dumps({"kids": [], "pixel_data": value}))
    (out / "page.html").write_text("<html><body></body></html>")
''')
    width, height = 20, 16
    image = Image.new(mode, (width, height))
    if mode == "L":
        pixels = [(x * 7 + y * 3) % 256 for y in range(height) for x in range(width)]
    elif mode == "RGB":
        pixels = [((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256)
                  for y in range(height) for x in range(width)]
    else:
        pixels = [((x * 7) % 256, (y * 11) % 256, ((x + y) * 5) % 256,
                   (x * 13 + y * 17) % 256) for y in range(height) for x in range(width)]
    image.putdata(pixels)
    source = tmp_path / "input.png"
    image.save(source)

    (request,) = odl.OpenDataLoader().requests(frozenset({"html", "blocks"}))
    got = odl.call(source, request, timeout=10)
    embedded = got.raw["json"]["pixel_data"]
    color = base64.b64decode(embedded["color"])
    alpha = base64.b64decode(embedded["alpha"])
    channels = 1 if mode == "L" else 3
    decoded = (bytes(channel for i in range(width * height)
                     for channel in (*color[i * 3:(i + 1) * 3], alpha[i])) if mode == "RGBA" else color)
    assert embedded["width"] == width and embedded["height"] == height
    assert len(color) == width * height * channels
    assert (mode == "RGBA") == bool(alpha)
    assert decoded == image.tobytes()
    assert embedded["page_width"] == pytest.approx(width)
    assert embedded["page_height"] == pytest.approx(height)


def test_production_child_parses_fake_vendor_outputs_without_vendor_package(tmp_path, monkeypatch):
    _child_env(monkeypatch, tmp_path)
    _fake_vendor(tmp_path, '''
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
def convert(input_path, output_dir, **kwargs):
    out = Path(output_dir); out.mkdir(parents=True)
    (out / "page.json").write_text(json.dumps({"kids": [
        {"type":"paragraph", "bounding box":[1,2,5,6], "content":"fake child"}]}))
    (out / "page.html").write_text("<html><body><p>fake child</p></body></html>")
''')
    pdf = tmp_path / "page.pdf"
    _blank_pdf(pdf)
    (request,) = odl.OpenDataLoader().requests(frozenset({"html", "blocks"}))
    got = odl.call(pdf, request, timeout=10)
    outputs, errs = odl.parse(got.raw, request)
    assert errs == {}
    assert outputs["html"] == "<p>fake child</p>"
    assert outputs["blocks"][0]["text"] == "fake child"


def test_missing_package_has_install_hint_without_vendor_package(tmp_path, monkeypatch):
    _child_env(monkeypatch, tmp_path)
    (tmp_path / "sitecustomize.py").write_text('''
import importlib.abc, sys
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "opendataloader_pdf":
            raise ModuleNotFoundError("blocked for test", name=fullname)
sys.meta_path.insert(0, Block())
''')
    pdf = tmp_path / "page.pdf"
    _blank_pdf(pdf)
    (request,) = odl.OpenDataLoader().requests(frozenset({"html"}))
    with pytest.raises(FileNotFoundError, match=r"pip install 'omni-parse-bench\[opendataloader\]'"):
        odl.call(pdf, request, timeout=10)


def test_missing_java_has_actionable_hint_without_java(tmp_path, monkeypatch):
    _child_env(monkeypatch, tmp_path)
    _fake_vendor(tmp_path, '''
def convert(**kwargs):
    raise FileNotFoundError(2, "No such file or directory", "java")
''')
    pdf = tmp_path / "page.pdf"
    _blank_pdf(pdf)
    (request,) = odl.OpenDataLoader().requests(frozenset({"html"}))
    with pytest.raises(FileNotFoundError, match="Java 11 or later"):
        odl.call(pdf, request, timeout=10)


def test_cold_version_lookup_timeout_is_bounded_without_vendor_package(tmp_path, monkeypatch):
    _child_env(monkeypatch, tmp_path)
    _fake_vendor(tmp_path, "def convert(**kwargs): raise AssertionError('conversion must not start')")
    (tmp_path / "sitecustomize.py").write_text('''
import importlib.metadata, time
original = importlib.metadata.version
def version(name):
    if name == "opendataloader-pdf": time.sleep(3)
    return original(name)
importlib.metadata.version = version
''')
    pdf = tmp_path / "page.pdf"
    _blank_pdf(pdf)
    (request,) = odl.OpenDataLoader().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout):
        odl.call(pdf, request, timeout=0.35)


def test_conversion_timeout_kills_the_java_process_group(tmp_path, monkeypatch):
    _child_env(monkeypatch, tmp_path)
    child_pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("ODL_CHILD_PID", str(child_pid_file))
    _fake_vendor(tmp_path, '''
import os, subprocess, sys, time
def convert(**kwargs):
    child = ("import os,pathlib,time; path=" + repr(os.environ["ODL_CHILD_PID"])
             + "; pathlib.Path(path).write_text(str(os.getpid())); time.sleep(120)")
    subprocess.Popen([sys.executable, "-c", child])
    time.sleep(120)
''')
    pdf = tmp_path / "page.pdf"
    _blank_pdf(pdf)
    (request,) = odl.OpenDataLoader().requests(frozenset({"html"}))

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(odl.call, pdf, request, timeout=20)
        deadline = time.monotonic() + 15
        while not child_pid_file.exists():
            if future.done():
                future.result()
            if time.monotonic() >= deadline:
                pytest.fail("OpenDataLoader worker did not start its child process")
            time.sleep(0.05)
        child_pid = int(child_pid_file.read_text())
        with pytest.raises(errors.SystemTimeout):
            future.result(timeout=25)

    deadline = time.monotonic() + 5
    while True:
        try:
            os.kill(child_pid, 0)
        except ProcessLookupError:
            break
        if time.monotonic() >= deadline:
            pytest.fail(f"OpenDataLoader descendant {child_pid} survived process-group termination")
        time.sleep(0.05)
