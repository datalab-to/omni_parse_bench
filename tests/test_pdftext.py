"""The pdftext adapter: its request, its html, a page with no text layer, and a real one-page PDF read."""
from __future__ import annotations

import pytest
import subprocess

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_parse_bench import harness  # noqa: E402
from omni_parse_bench.harness import contract, errors  # noqa: E402
from omni_parse_bench.harness.providers import pdftext_plain  # noqa: E402


def test_pdftext_asks_html_only_at_the_packages_defaults():
    cls = harness.ADAPTERS["pdftext"]
    assert cls.SUPPORTS == {"html"}
    (r,) = harness.system("pdftext").requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["html"]
    assert r.sent == {"package": "pdftext==0.7.1", "settings": {"sort": False, "hyphens": False}}


def test_text_is_written_as_escaped_html_and_no_text_layer_is_an_empty_page():
    (r,) = harness.system("pdftext").requests(frozenset({"html"}))
    assert pdftext_plain.parse({"text": "a < b & c\n"}, r)[0] == {"html": "<pre>a &lt; b &amp; c\n</pre>"}
    assert pdftext_plain.parse({"text": "  \n"}, r)[0] == {"html": ""}
    assert pdftext_plain.parse({"text": None}, r) == ({"html": ""}, {})


def test_an_image_has_no_text_layer(tmp_path):
    cfg = harness.system("pdftext")
    (r,) = cfg.requests(frozenset({"html"}))
    from omni_parse_bench.harness.providers import pdftext_plain
    pdftext_plain._VERSION[:] = ["0.7.1"]
    got = pdftext_plain.call(tmp_path / "scan.png", r, config=cfg)
    assert got.raw["text"] is None and got.cost.usd == 0.0


def _pdf(text: str) -> bytes:
    """A one-page PDF whose text layer is `text`, in Helvetica."""
    objs = ["<< /Type /Catalog /Pages 2 0 R >>", "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] /Contents 4 0 R "
            "/Resources << /Font << /F1 5 0 R >> >> >>", None,
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    stream = f"BT /F1 12 Tf 10 50 Td ({text}) Tj ET"
    objs[3] = f"<< /Length {len(stream)} >>\nstream\n{stream}\nendstream"
    out, offsets = "%PDF-1.4\n", []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n{o}\nendobj\n"
    xref = len(out)
    out += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n"
    out += "".join(f"{o:010d} 00000 n \n" for o in offsets)
    out += f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n"
    return out.encode()


def test_a_pdf_page_is_read_from_its_text_layer(tmp_path):
    pytest.importorskip("pdftext")
    path = tmp_path / "p.pdf"
    path.write_bytes(_pdf("Hello text layer"))
    cfg = harness.system("pdftext")
    (r,) = cfg.requests(frozenset({"html"}))
    got = pdftext_plain.call(path, r, config=cfg)
    assert got.raw["text"].strip() == "Hello text layer"
    assert pdftext_plain.parse(got.raw, r)[0] == {"html": "<pre>Hello text layer</pre>"}


def test_a_pdf_pdftext_cannot_open_is_the_pages_failure(tmp_path):
    pytest.importorskip("pdftext")
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    cfg = harness.system("pdftext")
    (r,) = cfg.requests(frozenset({"html"}))
    with pytest.raises(errors.SystemFailed, match="pdftext failed"):
        pdftext_plain.call(bad, r, config=cfg)
    assert isinstance(r, contract.Request)


def test_version_timeout_is_a_page_system_timeout_with_a_cold_cache(monkeypatch, tmp_path):
    from omni_parse_bench.harness.providers import pdftext_plain
    pdftext_plain._VERSION.clear()
    seen = []

    def slow(cmd, **kw):
        seen.append(kw["timeout"])
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(pdftext_plain.subprocess, "run", slow)
    (r,) = harness.system("pdftext").requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="version lookup ran past"):
        pdftext_plain.call(tmp_path / "page.pdf", r, config=harness.system("pdftext"), timeout=5)
    assert seen and seen[0] <= 5


def test_extraction_timeout_is_a_page_system_timeout(monkeypatch, tmp_path):
    from omni_parse_bench.harness.providers import pdftext_plain
    pdftext_plain._VERSION[:] = ["0.7.1"]
    seen = []

    def slow(cmd, **kw):
        seen.append(kw["timeout"])
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(pdftext_plain.subprocess, "run", slow)
    (r,) = harness.system("pdftext").requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="extraction ran past"):
        pdftext_plain.call(tmp_path / "page.pdf", r, config=harness.system("pdftext"), timeout=5)
    assert seen and seen[0] <= 5


def test_a_missing_or_unimportable_pdftext_package_is_reported(monkeypatch, tmp_path):
    from omni_parse_bench.harness.providers import pdftext_plain
    pdftext_plain._VERSION.clear()
    monkeypatch.setattr(pdftext_plain.subprocess, "run", lambda *a, **k:
                        subprocess.CompletedProcess(a[0], 1, "", "PackageNotFoundError: pdftext"))
    (r,) = harness.system("pdftext").requests(frozenset({"html"}))
    with pytest.raises(FileNotFoundError, match="pdftext isn't installed or importable"):
        pdftext_plain.call(tmp_path / "page.pdf", r, config=harness.system("pdftext"))
