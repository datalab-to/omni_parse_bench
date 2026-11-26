"""pdf-inspector: its Markdown as html, and its two modes' calls, from recorded answers (no OCR runtime)."""
from __future__ import annotations

import pytest

pytest.importorskip("httpx")
pytest.importorskip("pypdfium2")

from omni_parse_bench.harness import contract  # noqa: E402
from omni_parse_bench.harness.providers import pdf_inspector as pi  # noqa: E402

PIPE = "# Title\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\ntext"


def test_text_mode_is_the_default_and_calls_process_pdf():
    (r,) = pi.PdfInspector().requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["html"] and r.sent["function"] == "process_pdf" and r.sent["ocr"] == "off"
    assert pi.PdfInspector().provider == "pdf-inspector"
    assert pi.PdfInspector.SUPPORTS == frozenset({"html"})


def test_ocr_mode_is_its_own_row_with_the_packages_default_mode():
    c = pi.PdfInspector(ocr="auto")
    (r,) = c.requests(frozenset({"html"}))
    assert r.sent["function"] == "process_pdf_with_ocr" and r.sent["ocr"] == "auto"
    assert c.provider == "pdf-inspector-ocr"


def test_an_unknown_ocr_mode_is_refused():
    with pytest.raises(ValueError, match="ocr is one of"):
        pi.PdfInspector(ocr="maybe")


def test_markdown_becomes_html_with_its_table():
    (r,) = pi.PdfInspector().requests(frozenset({"html"}))
    outs, errs = pi.parse({"markdown": PIPE}, r)
    assert errs == {} and "<h1>Title</h1>" in outs["html"] and "<td>2</td>" in outs["html"]


@pytest.mark.parametrize("md", [None, "", "  \n"])
def test_a_page_with_no_markdown_is_an_empty_page(md):
    (r,) = pi.PdfInspector().requests(frozenset({"html"}))
    assert pi.parse({"markdown": md}, r) == ({"html": ""}, {})


def _fake(monkeypatch, tmp_path, ocr, calls):
    import json

    monkeypatch.setattr(pi, "version", lambda _: pi.PACKAGE.split("==")[1])

    def run(script, args, deadline, stage):
        function = "process_pdf" if args[1] == "off" else "process_pdf_with_ocr"
        calls.append((function, args))
        raw = ({"markdown": "hi", "pdf_type": "text_based", "confidence": 1.0} if ocr == "off" else
               {"markdown": "ocr text", "routed_to_ocr": [1],
                "pages": [{"page": 1, "source": "ocr", "confidence": 0.9}]})
        return pi.subprocess.CompletedProcess([], 0, json.dumps(raw), "")

    monkeypatch.setattr(pi, "run_python", run)
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF-1.4\n")
    c = pi.PdfInspector(ocr=ocr)
    (r,) = c.requests(frozenset({"html"}))
    return pi.call(pdf, r, config=c)


def test_text_mode_calls_process_pdf_and_is_free(monkeypatch, tmp_path):
    calls: list = []
    got = _fake(monkeypatch, tmp_path, "off", calls)
    assert calls[0][0] == "process_pdf" and got.raw["markdown"] == "hi" and got.cost.usd == 0.0


def test_ocr_mode_calls_process_pdf_with_ocr_at_the_packages_mode(monkeypatch, tmp_path):
    calls: list = []
    got = _fake(monkeypatch, tmp_path, "auto", calls)
    assert calls == [("process_pdf_with_ocr", [str(tmp_path / "p.pdf"), "auto", str(pi.DPI)])]
    assert got.raw["routed_to_ocr"] == [1] and got.raw["pages"][0]["source"] == "ocr"
    (r,) = pi.PdfInspector(ocr="auto").requests(frozenset({"html"}))
    assert pi.parse(got.raw, contract.Request(r.outputs, r.sent))[0] == {"html": "<p>ocr text</p>\n"}


@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA"])
def test_image_pdf_embedding_preserves_exact_pixels_and_alpha(mode, tmp_path):
    import pikepdf
    from PIL import Image

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
    source = tmp_path / f"{mode}.png"
    dest = tmp_path / "page.pdf"
    image.save(source)
    pi.as_pdf(source, dest)

    with pikepdf.Pdf.open(dest) as pdf:
        page = pdf.pages[0]
        xobject = next(iter(page.Resources.XObject.values()))
        assert int(xobject.Width) == width and int(xobject.Height) == height
        channels = 1 if mode == "L" else 3
        color = xobject.read_bytes()
        assert len(color) == width * height * channels
        if mode == "RGBA":
            alpha = xobject.SMask.read_bytes()
            assert len(alpha) == width * height
            decoded = bytes(channel for i in range(width * height)
                            for channel in (*color[i * 3:(i + 1) * 3], alpha[i]))
        else:
            decoded = color
        assert decoded == image.tobytes()
        box = page.MediaBox
        assert float(box[2]) - float(box[0]) == pytest.approx(width * 72 / pi.DPI)
        assert float(box[3]) - float(box[1]) == pytest.approx(height * 72 / pi.DPI)


@pytest.mark.parametrize("ocr", ["off", "auto"])
@pytest.mark.parametrize("mode", ["RGB", "L", "RGBA"])
def test_production_subprocess_passes_lossless_image_pdf_to_vendor(ocr, mode, tmp_path, monkeypatch):
    import base64
    import json
    import os
    from PIL import Image

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
    source = tmp_path / f"{mode}.png"
    image.save(source)

    # The child imports this fake vendor module, which inspects the exact temporary PDF it receives.
    fake_vendor = tmp_path / "pdf_inspector.py"
    fake_vendor.write_text('''
import base64, json, pikepdf
from types import SimpleNamespace
def process_pdf(path):
    with pikepdf.Pdf.open(path) as pdf:
        page = pdf.pages[0]
        xobject = next(iter(page.Resources.XObject.values()))
        color = xobject.read_bytes()
        alpha = xobject.SMask.read_bytes() if "/SMask" in xobject else b""
        box = page.MediaBox
        markdown = json.dumps({"width": int(xobject.Width), "height": int(xobject.Height),
                               "color": base64.b64encode(color).decode(),
                               "alpha": base64.b64encode(alpha).decode(),
                               "page_width": float(box[2]) - float(box[0]),
                               "page_height": float(box[3]) - float(box[1])})
    return SimpleNamespace(markdown=markdown, pdf_type="image_based", confidence=1.0,
                           pages_routed_to_ocr=[], pages=[])
def process_pdf_with_ocr(path, mode):
    return process_pdf(path)
''')
    inherited = os.environ.get("PYTHONPATH", "")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path) + (os.pathsep + inherited if inherited else ""))
    monkeypatch.setattr(pi, "version", lambda _: pi.PACKAGE.split("==")[1])
    config = pi.PdfInspector(ocr=ocr)
    (request,) = config.requests(frozenset({"html"}))

    got = pi.call(source, request, config=config)
    embedded = json.loads(got.raw["markdown"])
    color = base64.b64decode(embedded["color"])
    alpha = base64.b64decode(embedded["alpha"])
    channels = 1 if mode == "L" else 3
    if mode == "RGBA":
        decoded = bytes(channel for i in range(width * height)
                        for channel in (*color[i * 3:(i + 1) * 3], alpha[i]))
    else:
        decoded = color
    assert embedded["width"] == width and embedded["height"] == height
    assert len(color) == width * height * channels
    assert (mode == "RGBA") == bool(alpha)
    assert decoded == image.tobytes()
    assert embedded["page_width"] == pytest.approx(width * 72 / pi.DPI)
    assert embedded["page_height"] == pytest.approx(height * 72 / pi.DPI)


class _HungProcess:
    pid = 1234
    returncode = -9

    def communicate(self, timeout=None):
        if timeout is not None:
            raise pi.subprocess.TimeoutExpired("python", timeout)
        return "", ""


def test_cold_version_lookup_timeout_kills_process_group(monkeypatch):
    pi._VERSION.clear()
    proc = _HungProcess()
    monkeypatch.setattr(pi.subprocess, "Popen", lambda *a, **kw: proc)
    killed = []
    monkeypatch.setattr(pi.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    with pytest.raises(pi.errors.SystemTimeout, match="version lookup"):
        pi.version(pi.budget.Budget(0.01))
    assert killed == [(proc.pid, pi.signal.SIGKILL)]


def test_extraction_timeout_is_system_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(pi, "version", lambda _: pi.PACKAGE.split("==")[1])
    proc = _HungProcess()
    monkeypatch.setattr(pi.subprocess, "Popen", lambda *a, **kw: proc)
    monkeypatch.setattr(pi.os, "killpg", lambda *_: None)
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    (request,) = pi.PdfInspector().requests(frozenset({"html"}))
    with pytest.raises(pi.errors.SystemTimeout, match="page extraction"):
        pi.call(pdf, request, timeout=0.01)


def test_missing_package_has_install_hint_without_package_installed(monkeypatch):
    pi._VERSION.clear()

    class MissingPackage:
        pid = 23
        returncode = 1

        def communicate(self, timeout=None):
            return "", "ModuleNotFoundError: No module named 'pdf_inspector'"

    monkeypatch.setattr(pi.subprocess, "Popen", lambda *a, **kw: MissingPackage())
    with pytest.raises(FileNotFoundError, match=r"pip install 'omni-parse-bench\[pdf-inspector\]'"):
        pi.version(pi.budget.Budget(1))


def test_missing_ocr_runtime_has_actionable_library_hint(monkeypatch, tmp_path):
    monkeypatch.setattr(pi, "version", lambda _: pi.PACKAGE.split("==")[1])
    monkeypatch.setattr(
        pi, "run_python",
        lambda *a: pi.subprocess.CompletedProcess([], 1, "", "OSError: libonnxruntime not found"),
    )
    pdf = tmp_path / "p.pdf"
    pdf.write_bytes(b"%PDF")
    c = pi.PdfInspector(ocr="auto")
    (request,) = c.requests(frozenset({"html"}))
    with pytest.raises(RuntimeError, match="install PDFium and ONNX Runtime 1.27.0"):
        pi.call(pdf, request, config=c)
