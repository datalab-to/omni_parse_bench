"""The MarkItDown adapter's request, HTML conversion, deadlines, and missing-package handling."""
from __future__ import annotations

import json
import subprocess

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_parse_bench.harness import errors  # noqa: E402
from omni_parse_bench.harness.providers import markitdown  # noqa: E402


class FakeProcess:
    pid = 321

    def __init__(self, stdout="", stderr="", returncode=0, timeout=False):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode
        self.should_timeout = timeout
        self.timeouts = []

    def communicate(self, timeout=None):
        self.timeouts.append(timeout)
        if self.should_timeout:
            self.should_timeout = False
            raise subprocess.TimeoutExpired("python", timeout)
        return self.stdout, self.stderr


def fake_processes(monkeypatch, processes):
    calls = []

    def popen(command, **kwargs):
        process = processes.pop(0)
        calls.append((command, kwargs, process))
        return process

    killed = []
    monkeypatch.setattr(markitdown.subprocess, "Popen", popen)
    monkeypatch.setattr(markitdown.os, "killpg", lambda pid, sig: killed.append((pid, sig)))
    return calls, killed


def test_markitdown_asks_for_html_only_and_says_html_is_derived():
    [r] = markitdown.MarkItDown().requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["html"] and "derived" in r.sent and set(r.sent) == {"derived"}


def test_markitdown_markdown_goes_through_the_shared_converter():
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    outs, errs = markitdown.parse({"markdown": "# T\n\na < b"}, r)
    assert outs["html"].startswith("<h1>T</h1>") and "a &lt; b" in outs["html"] and errs == {}


def test_a_page_is_converted_in_a_killable_process_group_with_no_options(monkeypatch, tmp_path):
    monkeypatch.setattr(markitdown, "_VERSION", [])
    result = json.dumps({"markdown": "hello", "exiftool": True})
    version_proc = FakeProcess(stdout="0.1.9\n")
    conversion_proc = FakeProcess(stdout=result)
    calls, killed = fake_processes(monkeypatch, [version_proc, conversion_proc])
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    got = markitdown.call(tmp_path / "p.pdf", r, timeout=5)
    assert got.raw == {"markdown": "hello", "version": "markitdown 0.1.9", "exiftool": True}
    assert got.cost.usd == 0.0 and len(calls) == 2 and not killed
    assert all(kwargs["start_new_session"] for _, kwargs, _ in calls)
    assert calls[0][2].timeouts[0] <= 5 and calls[1][2].timeouts[0] <= 5
    assert str(tmp_path / "p.pdf") in calls[1][0]


def test_a_version_lookup_timeout_is_a_system_timeout_with_a_cold_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(markitdown, "_VERSION", [])
    process = FakeProcess(timeout=True)
    calls, killed = fake_processes(monkeypatch, [process])
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="version lookup ran past"):
        markitdown.call(tmp_path / "p.pdf", r, timeout=5)
    assert process.timeouts[0] <= 5 and killed == [(process.pid, markitdown.signal.SIGKILL)]
    assert calls[0][1]["start_new_session"] is True


def test_a_conversion_timeout_is_a_system_timeout_and_kills_the_process_group(monkeypatch, tmp_path):
    monkeypatch.setattr(markitdown, "_VERSION", ["markitdown 0.1.9"])
    process = FakeProcess(timeout=True)
    calls, killed = fake_processes(monkeypatch, [process])
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemTimeout, match="conversion ran past"):
        markitdown.call(tmp_path / "p.pdf", r, timeout=5)
    assert process.timeouts[0] <= 5 and killed == [(process.pid, markitdown.signal.SIGKILL)]
    assert calls[0][1]["start_new_session"] is True


def test_a_conversion_that_raises_fails_the_page(monkeypatch, tmp_path):
    monkeypatch.setattr(markitdown, "_VERSION", ["markitdown 0.1.9"])
    _, _ = fake_processes(monkeypatch, [FakeProcess(stderr="ValueError: bad pdf", returncode=1)])
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    with pytest.raises(errors.SystemFailed, match="ValueError: bad pdf"):
        markitdown.call(tmp_path / "p.pdf", r)


def test_a_missing_package_says_how_to_install_it_without_the_package(monkeypatch, tmp_path):
    monkeypatch.setattr(markitdown, "_VERSION", [])
    fake_processes(monkeypatch, [FakeProcess(stderr="PackageNotFoundError: markitdown", returncode=1)])
    [r] = markitdown.MarkItDown().requests(frozenset({"html"}))
    with pytest.raises(FileNotFoundError, match=r"omni-parse-bench\[markitdown\]"):
        markitdown.call(tmp_path / "p.pdf", r)
