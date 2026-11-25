"""The pdftotext adapter: its request, its html, an image page and a failing binary (no binary needed)."""
from __future__ import annotations

import subprocess

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_parse_bench.harness import errors  # noqa: E402
from omni_parse_bench.harness.providers import pdftotext  # noqa: E402


def test_pdftotext_asks_for_html_only_and_sends_no_options():
    [r] = pdftotext.Pdftotext().requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["html"] and r.sent == {}


def test_pdftotext_writes_its_text_as_escaped_html():
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    outs, errs = pdftotext.parse({"text": "a < b & c\n\f"}, r)
    assert outs == {"html": "<pre>a &lt; b &amp; c\n\f</pre>"} and errs == {}


def test_an_image_page_has_no_text_layer_and_runs_nothing(monkeypatch, tmp_path):
    monkeypatch.setattr(pdftotext.subprocess, "run", lambda *a, **k: pytest.fail("ran a binary"))
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    got = pdftotext.call(tmp_path / "p.png", r)
    assert got.raw["text"] == "" and got.cost.usd == 0.0


def test_a_pdf_page_is_read_at_the_documented_default_without_layout(monkeypatch, tmp_path):
    seen = []

    def run(cmd, **kw):
        seen.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "hello", "")

    monkeypatch.setattr(pdftotext.shutil, "which", lambda _: "/bin/pdftotext")
    monkeypatch.setattr(pdftotext.subprocess, "run", run)
    monkeypatch.setattr(pdftotext, "version", lambda deadline: "pdftotext version 26")
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    got = pdftotext.call(tmp_path / "p.pdf", r)
    assert seen == [["pdftotext", str(tmp_path / "p.pdf"), "-"]]
    assert got.raw["text"] == "hello" and got.cost.usd == 0.0


def test_a_pdftotext_that_exits_with_an_error_fails_the_page(monkeypatch, tmp_path):
    monkeypatch.setattr(pdftotext.shutil, "which", lambda _: "/bin/pdftotext")
    monkeypatch.setattr(pdftotext.subprocess, "run",
                        lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "Syntax Error"))
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemFailed, match="exited 1: Syntax Error"):
        pdftotext.call(tmp_path / "p.pdf", r)


def test_a_pdftotext_past_the_pages_time_is_a_timeout(monkeypatch, tmp_path):
    def slow(cmd, **kw):
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(pdftotext.shutil, "which", lambda _: "/bin/pdftotext")
    monkeypatch.setattr(pdftotext, "version", lambda deadline: "pdftotext version 26")
    monkeypatch.setattr(pdftotext.subprocess, "run", slow)
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="pdftotext ran past"):
        pdftotext.call(tmp_path / "p.pdf", r, timeout=5)


def test_reading_the_version_is_bounded_by_the_pages_time(monkeypatch, tmp_path):
    seen = []

    def slow(cmd, **kw):
        seen.append(kw["timeout"])
        raise subprocess.TimeoutExpired(cmd, kw["timeout"])

    monkeypatch.setattr(pdftotext, "_VERSION", [])
    monkeypatch.setattr(pdftotext.shutil, "which", lambda _: "/bin/pdftotext")
    monkeypatch.setattr(pdftotext.subprocess, "run", slow)
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="pdftotext -v ran past"):
        pdftotext.call(tmp_path / "p.pdf", r, timeout=5)
    assert seen and seen[0] <= 5


def test_the_version_is_read_once(monkeypatch):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "pdftotext version 26.10.0\nCopyright")

    monkeypatch.setattr(pdftotext, "_VERSION", [])
    monkeypatch.setattr(pdftotext.subprocess, "run", run)
    d = pdftotext.budget.Budget(5)
    assert pdftotext.version(d) == pdftotext.version(d) == "pdftotext version 26.10.0" and len(calls) == 1


def test_a_missing_binary_is_reported(monkeypatch, tmp_path):
    monkeypatch.setattr(pdftotext.shutil, "which", lambda _: None)
    [r] = pdftotext.Pdftotext().requests(frozenset({"html"}))
    with pytest.raises(FileNotFoundError, match="brew install poppler"):
        pdftotext.call(tmp_path / "p.pdf", r)
