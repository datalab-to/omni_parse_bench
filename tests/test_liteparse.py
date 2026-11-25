"""LiteParse: its answer as html and blocks, its two rows, and its settings, from recorded answers (the
package need not be installed)."""
from __future__ import annotations

import os
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from omni_parse_bench.harness import errors  # noqa: E402
from omni_parse_bench.harness.providers import liteparse as lp  # noqa: E402

BOTH = frozenset({"html", "blocks"})


def box(x, y, w, h):
    return {"x": x, "y": y, "width": w, "height": h}


# Shaped like the package's `dataclasses.asdict(LayoutBlock)`; the page is 600 x 800 points.
ANSWER = {
    "markdown": "# Title\n\nBody text\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nPage 3 of 9",
    "width": 600.0, "height": 800.0, "version": "liteparse 2.21.1, text layer, no OCR",
    "blocks": [
        {"kind": "heading", "text": "Title", "bbox": box(60, 80, 300, 40)},
        {"kind": "paragraph", "text": "Body text", "bbox": box(60, 160, 300, 40)},
        {"kind": "list_item", "text": "- one", "bbox": box(60, 200, 120, 20)},
        {"kind": "code", "lines": ["x = 1", "y = 2"], "bbox": box(60, 240, 120, 40)},
        {"kind": "grid_fallback", "lines": ["a   b", "c   d"], "bbox": box(60, 300, 120, 40)},
        {"kind": "table", "header": [{"text": "a"}, {"text": "b"}], "rows": [[{"text": "1"}, {"text": None}]],
         "bbox": box(60, 360, 300, 40)},
        {"kind": "figure", "id": "img_1", "format": "png", "bbox": box(300, 400, 300, 400)},
        {"kind": "rule", "bbox": box(0, 700, 600, 1)},
        {"kind": "paragraph", "text": "Page 3 of 9", "bbox": box(250, 760, 100, 20)},
        {"kind": "paragraph", "text": "no box", "bbox": None},
    ],
}


def read(raw=ANSWER, *, config=None, wants=BOTH):
    (r,) = (config or lp.LiteParse()).requests(wants)
    return lp.parse(raw, r)


def test_the_two_modes_are_two_rows_with_their_documented_settings():
    text, ocr = lp.LiteParse(), lp.LiteParse(ocr=True)
    assert (text.provider, ocr.provider) == ("liteparse", "liteparse-tesseract")
    assert lp.LiteParse.name == "liteparse" and lp.LiteParse.SUPPORTS == BOTH
    (a,), (b,) = text.requests(BOTH), ocr.requests(BOTH)
    assert a.sent["ocr_enabled"] is False and b.sent["ocr_enabled"] is True
    for r in (a, b):
        assert r.sent["ocr_backend"] == "tesseract" and r.sent["output_format"] == "markdown"
        assert r.sent["extract_blocks"] is True and r.sent["package"] == "liteparse==2.21.1"
    assert text.requests(frozenset()) == []


def test_the_ocria_nano_row_is_its_own_row_with_its_backend_and_needs_ocr():
    nano = lp.LiteParse(ocr=True, ocr_backend="ocria-nano")
    assert nano.provider == "liteparse-ocria-nano" and lp.LiteParse.name == "liteparse"
    (r,) = nano.requests(BOTH)
    assert r.sent["ocr_enabled"] is True and r.sent["ocr_backend"] == "ocria-nano"
    assert "dpi" not in r.sent and "ocr_language" not in r.sent  # the package's defaults: 250 dpi with it
    assert read(config=nano)[0]["blocks"][0]["label"] == "heading"
    with pytest.raises(ValueError, match="ocr=true"):
        lp.LiteParse(ocr_backend="ocria-nano")
    with pytest.raises(ValueError, match="ocr_backend must be one of"):
        lp.LiteParse(ocr=True, ocr_backend="paddle")


def test_html_is_the_markdown_with_its_table_and_its_page_number_kept():
    outs, errs = read()
    assert errs == {} and "<h1>Title</h1>" in outs["html"] and "<td>2</td>" in outs["html"]
    assert "Page 3 of 9" in outs["html"]


@pytest.mark.parametrize("md", ["", "  \n"])
def test_a_page_with_no_markdown_is_an_empty_page(md):
    assert read(ANSWER | {"markdown": md}, wants=frozenset({"html"}))[0] == {"html": ""}


def test_blocks_are_labelled_boxed_and_kept_in_order():
    blocks = read()[0]["blocks"]
    labels = ["heading", "text", "list", "code", "text", "table", "figure", "text"]
    assert [b["label"] for b in blocks] == labels
    assert blocks[0]["bbox"] == [0.1, 0.1, 0.6, 0.15]
    assert blocks[3]["text"] == "x = 1\ny = 2" and blocks[4]["text"] == "a   b\nc   d"
    assert blocks[5]["text"] == "a | b\n1 | " and blocks[6]["text"] == ""
    # the page's header and footer are kept, and are ordinary text: LiteParse has no class for them
    assert blocks[-1] == {"label": "text", "bbox": [250 / 600, 0.95, 350 / 600, 0.975], "text": "Page 3 of 9"}


def test_rules_and_boxless_blocks_are_not_blocks_and_nothing_else_is_dropped():
    blocks = read()[0]["blocks"]
    assert len(ANSWER["blocks"]) - len(blocks) == 2
    assert not any(b["text"] == "no box" for b in blocks)


def test_no_class_maps_to_caption_footnote_equation_or_form_and_page_furniture_is_ocria_nanos_alone():
    assert not {"caption", "footnote", "equation", "form"} & set(lp.LABELS.values())
    assert set(lp.LABELS.values()) <= {"text", "heading", "list", "code", "table", "figure", "page_furniture"}
    assert {k for k, v in lp.LABELS.items() if v == "page_furniture"} == {"page_header", "page_footer"}


def test_the_kinds_only_ocria_nano_emits_are_mapped_as_documented():
    nano = [{"kind": "merged_table", "rows": [[{"text": "a"}, {"text": "b"}]], "bbox": box(0, 0, 60, 80)},
            {"kind": "page_header", "text": "Journal 12", "bbox": box(0, 0, 60, 8)},
            {"kind": "page_footer", "text": "3", "bbox": box(0, 792, 60, 8)}]
    blocks = read(ANSWER | {"blocks": nano})[0]["blocks"]
    assert [b["label"] for b in blocks] == ["table", "page_furniture", "page_furniture"]
    assert blocks[0]["text"] == "a | b" and blocks[1]["text"] == "Journal 12"


def test_an_unknown_block_kind_fails_blocks_without_losing_requested_html():
    outputs, errs = read(ANSWER | {"blocks": [{"kind": "caption", "text": "x", "bbox": box(0, 0, 1, 1)}]})
    assert "<h1>Title</h1>" in outputs["html"] and "blocks" not in outputs
    assert "SystemFailed" in errs["blocks"] and "caption" in errs["blocks"]


def test_a_malformed_block_fails_blocks_without_losing_requested_html():
    outputs, errs = read(ANSWER | {"blocks": [{"kind": "heading", "text": "x", "bbox": {"x": 0}}]})
    assert "<h1>Title</h1>" in outputs["html"] and "blocks" not in outputs
    assert "SystemFailed" in errs["blocks"]


def test_a_blocks_only_request_leaves_html_out():
    outs, _ = read(wants=frozenset({"blocks"}))
    assert sorted(outs) == ["blocks"]


FAKE_LITEPARSE = '''
import dataclasses, json, os, subprocess, sys, time
from pathlib import Path

class ParseError(Exception): pass
class ParseTimeoutError(Exception): pass

@dataclasses.dataclass
class Box:
    x: float
    y: float
    width: float
    height: float

@dataclasses.dataclass
class Block:
    kind: str
    text: str | None = None
    lines: list | None = None
    header: list | None = None
    rows: list | None = None
    bbox: Box | None = None

@dataclasses.dataclass
class Page:
    markdown: str
    width: float
    height: float
    blocks: list

@dataclasses.dataclass
class Result:
    pages: list

class LiteParse:
    def __init__(self, **kwargs):
        config_file = os.environ.get("LITEPARSE_CONFIG_FILE")
        if config_file: Path(config_file).write_text(json.dumps(kwargs))
    def parse(self, path):
        mode = os.environ.get("LITEPARSE_FAKE_MODE")
        if mode == "spawn":
            child_pid = os.environ["LITEPARSE_CHILD_PID"]
            child = (
                "import os,pathlib,time; pathlib.Path(" + repr(child_pid)
                + ").write_text(str(os.getpid())); time.sleep(120)"
            )
            subprocess.Popen([sys.executable, "-c", child])
            time.sleep(120)
        if mode == "timeout": raise ParseTimeoutError("fake vendor timeout")
        if mode == "error": raise ParseError("fake vendor error")
        text = Path(path).read_bytes().hex()
        return Result([Page(text, 600.0, 800.0, [Block("paragraph", text, bbox=Box(0, 0, 6, 8))])])
    def close(self): pass
'''

FAKE_MODELS = '''
import os
from types import SimpleNamespace
def list():
    complete = os.environ.get("LITEPARSE_MODELS_COMPLETE") == "1"
    return [SimpleNamespace(name="ocria-nano", version="1.0.0", complete=complete)]
'''


def fake_liteparse(tmp_path, monkeypatch, *, version="2.21.1"):
    root = tmp_path / "fake-site"
    package = root / "liteparse"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text(FAKE_LITEPARSE)
    (package / "models.py").write_text(FAKE_MODELS)
    dist = root / f"liteparse-{version}.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text(f"Name: liteparse\nVersion: {version}\n")
    current = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(root), current])))
    return root


def request_for(config=None):
    config = config or lp.LiteParse()
    (request,) = config.requests(BOTH)
    return request


def test_the_real_child_path_uses_the_fake_vendor_and_preserves_image_bytes(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch)
    image_bytes = b"\x89PNG\r\n\x1a\n\x00payload\xff"
    image = tmp_path / "page.png"
    image.write_bytes(image_bytes)
    config_file = tmp_path / "config.json"
    monkeypatch.setenv("LITEPARSE_CONFIG_FILE", str(config_file))
    config = lp.LiteParse(ocr=True)

    result = lp.call(image, request_for(config), timeout=10, config=config)

    assert result.raw["markdown"] == image_bytes.hex()
    assert result.raw["blocks"][0]["text"] == image_bytes.hex()
    assert result.cost.usd == 0.0
    assert lp.parse(result.raw, request_for(config))[0]["blocks"][0]["bbox"] == [0.0, 0.0, 0.01, 0.01]
    settings = __import__("json").loads(config_file.read_text())
    assert settings == {"ocr_enabled": True, "ocr_backend": "tesseract", "keep_headers_footers": True,
                        "output_format": "markdown", "extract_blocks": True, "quiet": True,
                        "num_workers": 1, "pool_size": lp.LiteParse.workers,
                        "parse_timeout": lp.PARSE_TIMEOUT}


def wait_for_file(path, future, timeout=15):
    deadline = time.monotonic() + timeout
    while not path.exists():
        if future.done():
            future.result()
        if time.monotonic() >= deadline:
            pytest.fail(f"worker did not create {path} within {timeout}s")
        time.sleep(0.05)


def test_cold_version_lookup_timeout_is_bounded(tmp_path, monkeypatch):
    root = fake_liteparse(tmp_path, monkeypatch)
    started = tmp_path / "version-lookup-started"
    (root / "sitecustomize.py").write_text('''
import importlib.metadata, os, pathlib, time
original = importlib.metadata.version
def version(name):
    if name == "liteparse" and os.environ.get("LITEPARSE_DELAY_VERSION"):
        pathlib.Path(os.environ["LITEPARSE_VERSION_STARTED"]).touch()
        time.sleep(120)
    return original(name)
importlib.metadata.version = version
''')
    monkeypatch.setenv("LITEPARSE_DELAY_VERSION", "1")
    monkeypatch.setenv("LITEPARSE_VERSION_STARTED", str(started))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\n")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lp.call, page, request_for(), timeout=20)
        wait_for_file(started, future)
        with pytest.raises(errors.SystemTimeout):
            future.result(timeout=25)


def test_conversion_timeout_kills_descendants_in_the_process_group(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch)
    child_pid_file = tmp_path / "child.pid"
    monkeypatch.setenv("LITEPARSE_FAKE_MODE", "spawn")
    monkeypatch.setenv("LITEPARSE_CHILD_PID", str(child_pid_file))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(lp.call, page, request_for(), timeout=20)
        wait_for_file(child_pid_file, future)
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
            pytest.fail(f"LiteParse descendant {child_pid} survived process-group termination")
        time.sleep(0.05)


def test_vendor_timeout_maps_to_system_timeout_and_parse_errors_fail_the_page(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch)
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")
    monkeypatch.setenv("LITEPARSE_FAKE_MODE", "timeout")
    with pytest.raises(errors.SystemTimeout, match="fake vendor timeout"):
        lp.call(page, request_for(), timeout=10)
    monkeypatch.setenv("LITEPARSE_FAKE_MODE", "error")
    with pytest.raises(errors.SystemFailed, match="fake vendor error"):
        lp.call(page, request_for(), timeout=10)


def test_missing_liteparse_has_an_actionable_hint_without_the_package(tmp_path, monkeypatch):
    site = tmp_path / "block-package"
    site.mkdir()
    (site / "sitecustomize.py").write_text('''
import importlib.metadata
original = importlib.metadata.version
def version(name):
    if name == "liteparse": raise importlib.metadata.PackageNotFoundError(name)
    return original(name)
importlib.metadata.version = version
''')
    current = os.environ.get("PYTHONPATH")
    monkeypatch.setenv("PYTHONPATH", os.pathsep.join(filter(None, [str(site), current])))
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")

    with pytest.raises(FileNotFoundError, match="omni-parse-bench\\[liteparse\\]"):
        lp.call(page, request_for(), timeout=10)


def test_missing_ocria_nano_models_have_an_actionable_hint(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch)
    monkeypatch.setenv("LITEPARSE_MODELS_COMPLETE", "0")
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")
    config = lp.LiteParse(ocr=True, ocr_backend="ocria-nano")

    with pytest.raises(FileNotFoundError, match="models.pull.*ocria-nano"):
        lp.call(page, request_for(config), timeout=10, config=config)


def test_ocria_nano_model_version_is_recorded_when_available(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch)
    monkeypatch.setenv("LITEPARSE_MODELS_COMPLETE", "1")
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")
    config = lp.LiteParse(ocr=True, ocr_backend="ocria-nano")

    result = lp.call(page, request_for(config), timeout=10, config=config)

    assert result.raw["version"] == "liteparse 2.21.1, OCR: ocria-nano 1.0.0"


def test_a_different_installed_version_is_rejected_in_the_child(tmp_path, monkeypatch):
    fake_liteparse(tmp_path, monkeypatch, version="2.22.0")
    page = tmp_path / "page.pdf"
    page.write_bytes(b"%PDF-1.4\\n")

    with pytest.raises(RuntimeError, match="this adapter is for liteparse==2.21.1"):
        lp.call(page, request_for(), timeout=10)
