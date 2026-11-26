"""The PyMuPDF4LLM adapter: its requests, its html, its layout boxes as blocks, and a failing call."""
from __future__ import annotations

import json
import os
import time

import pytest

from omni_parse_bench import views  # noqa: E402
from omni_parse_bench.harness import errors  # noqa: E402
from omni_parse_bench.harness.providers import pymupdf4llm as p4  # noqa: E402

JSON_PAGE = {"pages": [{"width": 200.0, "height": 400.0, "words": ["x"], "boxes": [
    {"boxclass": "section-header", "x0": 20, "y0": 40, "x1": 100, "y1": 60,
     "textlines": [{"spans": [{"text": " Big", "font": "A"}, {"text": " title"}]}]},
    {"boxclass": "table", "x0": 0, "y0": 100, "x1": 200, "y1": 200, "textlines": None,
     "table": {"extract": [["a", ""], ["b", "c"]], "markdown": "|a||"}},
    {"boxclass": "picture", "x0": 0, "y0": 300, "x1": 200, "y1": 400, "textlines": None, "table": None},
]}]}


def fake_package(tmp_path, monkeypatch, source):
    (tmp_path / "pymupdf4llm.py").write_text(source)
    for package in ("pymupdf4llm", "pymupdf"):
        info = tmp_path / f"{package}-2.1.dist-info"
        info.mkdir()
        (info / "METADATA").write_text(f"Metadata-Version: 2.1\nName: {package}\nVersion: 2.1\n")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join((str(tmp_path), os.environ.get("PYTHONPATH", ""))))


def test_every_label_is_a_real_label():
    assert set(p4.LABELS.values()) <= set(views.LABELS)


def test_html_and_blocks_are_two_calls_and_html_is_derived():
    rs = p4.PyMuPDF4LLM().requests(frozenset({"html", "blocks"}))
    assert [(sorted(r.outputs), r.sent["function"]) for r in rs] == [(["html"], "to_markdown"),
                                                                    (["blocks"], "to_json")]
    assert "derived" in rs[0].sent and "derived" not in rs[1].sent
    assert [r.sent["use_ocr"] for r in rs] == [False, False]  # the text-layer row
    assert len(p4.PyMuPDF4LLM().requests(frozenset({"html"}))) == 1


def test_markdown_goes_through_the_shared_converter():
    [r] = p4.PyMuPDF4LLM().requests(frozenset({"html"}))
    outs, errs = p4.parse({"markdown": "# T\n\na < b"}, r)
    assert outs["html"].startswith("<h1>T</h1>") and errs == {}


@pytest.mark.parametrize(("fn", "output"), [("to_markdown", "html"), ("to_json", "blocks")])
@pytest.mark.parametrize("use_ocr", [False, True])
def test_production_child_path_preserves_vendor_answers(monkeypatch, tmp_path, fn, output, use_ocr):
    vendor_json = json.dumps(JSON_PAGE, separators=(",", ":"))
    marker = tmp_path / "seen.json"
    source = f"""import json, os
VENDOR_JSON = {vendor_json!r}
def {fn}(path, use_ocr):
    open(os.environ['MARKER'], 'w').write(json.dumps([path, use_ocr]))
    return VENDOR_JSON if {fn!r} == 'to_json' else '# T\\n\\ntext'
"""
    fake_package(tmp_path, monkeypatch, source)
    monkeypatch.setenv("MARKER", str(marker))
    [request] = p4.PyMuPDF4LLM(use_ocr=use_ocr).requests(frozenset({output}))
    page = tmp_path / "input.pdf"
    page.touch()
    got = p4.call(page, request)
    assert json.loads(marker.read_text()) == [str(page), use_ocr]
    assert got.cost.usd == 0.0
    if output == "blocks":
        assert got.raw["json"] == vendor_json
        saved = json.loads(got.raw["json"])
        assert saved["pages"][0]["words"] == ["x"]
        assert saved["pages"][0]["boxes"][0]["textlines"][0]["spans"][0]["font"] == "A"
    outs, errs = p4.parse(got.raw, request)
    assert errs == {}
    if output == "blocks":
        assert outs["blocks"] == [
            {"label": "heading", "bbox": [0.1, 0.1, 0.5, 0.15], "text": "Big title"},
            {"label": "table", "bbox": [0.0, 0.25, 1.0, 0.5], "text": "a b c"},
            {"label": "figure", "bbox": [0.0, 0.75, 1.0, 1.0], "text": ""},
        ]
    else:
        assert outs["html"].startswith("<h1>T</h1>")


def test_a_class_the_table_lacks_fails_the_blocks_only():
    page = {"width": 10, "height": 10, "boxes": [{"boxclass": "mystery", "x0": 0, "y0": 0,
                                                     "x1": 1, "y1": 1, "textlines": []}]}
    [r] = p4.PyMuPDF4LLM().requests(frozenset({"blocks"}))
    outs, errs = p4.parse({"json": json.dumps({"pages": [page]})}, r)
    assert outs == {} and "mystery" in errs["blocks"]


def test_a_call_that_raises_fails_the_page(monkeypatch, tmp_path):
    fake_package(tmp_path, monkeypatch, "def to_markdown(path, use_ocr): raise RuntimeError('cannot open')\n")
    [r] = p4.PyMuPDF4LLM().requests(frozenset({"html"}))
    page = tmp_path / "p.pdf"
    page.touch()
    with pytest.raises(errors.SystemFailed, match="RuntimeError: cannot open"):
        p4.call(page, r)


def test_a_missing_package_says_how_to_install_it(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    (tmp_path / "sitecustomize.py").write_text("""import sys
class Block:
    def find_spec(self, fullname, *args):
        if fullname == 'pymupdf4llm':
            raise ModuleNotFoundError('blocked package', name=fullname)
sys.meta_path.insert(0, Block())
""")
    [r] = p4.PyMuPDF4LLM().requests(frozenset({"html"}))
    page = tmp_path / "p.pdf"
    page.touch()
    with pytest.raises(FileNotFoundError, match=r"omni-parse-bench\[pymupdf4llm\]"):
        p4.call(page, r)


@pytest.mark.parametrize(("fn", "output"), [("to_markdown", "html"), ("to_json", "blocks")])
@pytest.mark.parametrize("use_ocr", [False, True])
def test_cold_version_lookup_uses_page_timeout(monkeypatch, tmp_path, fn, output, use_ocr):
    answer = "'x'" if fn == "to_markdown" else f"{json.dumps(JSON_PAGE)!r}"
    fake_package(tmp_path, monkeypatch, f"def {fn}(path, use_ocr): return {answer}\n")
    (tmp_path / "sitecustomize.py").write_text("""import importlib.metadata, time
original = importlib.metadata.version
def slow(name):
    time.sleep(5)
    return original(name)
importlib.metadata.version = slow
""")
    [r] = p4.PyMuPDF4LLM(use_ocr=use_ocr).requests(frozenset({output}))
    page = tmp_path / "p.pdf"
    page.touch()
    with pytest.raises(errors.SystemTimeout):
        p4.call(page, r, timeout=0.2)


@pytest.mark.parametrize(("fn", "output"), [("to_markdown", "html"), ("to_json", "blocks")])
@pytest.mark.parametrize("use_ocr", [False, True])
def test_conversion_timeout_kills_child_process_group(monkeypatch, tmp_path, fn, output, use_ocr):
    marker = tmp_path / "survived"
    child_script = f"import pathlib,time; time.sleep(1); pathlib.Path({str(marker)!r}).write_text('yes')"
    source = f"""import subprocess, sys
def {fn}(path, use_ocr):
    child = subprocess.Popen([sys.executable, '-c', {child_script!r}])
    child.wait()
    return {json.dumps(JSON_PAGE)!r} if {fn!r} == 'to_json' else 'x'
"""
    fake_package(tmp_path, monkeypatch, source)
    [r] = p4.PyMuPDF4LLM(use_ocr=use_ocr).requests(frozenset({output}))
    page = tmp_path / "p.pdf"
    page.touch()
    with pytest.raises(errors.SystemTimeout):
        p4.call(page, r, timeout=0.4)
    time.sleep(1.1)
    assert not marker.exists()


def test_the_two_modes_are_two_rows():
    assert p4.PyMuPDF4LLM().provider == "pymupdf4llm"
    assert p4.PyMuPDF4LLM(use_ocr=True).provider == "pymupdf4llm-ocr"
    [r] = p4.PyMuPDF4LLM(use_ocr=True).requests(frozenset({"html"}))
    assert r.sent["use_ocr"] is True
