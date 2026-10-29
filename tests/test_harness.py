"""The adapters: each one's requests and parsing, and the rules every call follows, over a stub system (no
network)."""
from __future__ import annotations

import dataclasses
import json
import types
from typing import ClassVar

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_bench_core import adapter as core  # noqa: E402

from omni_parse_bench import harness  # noqa: E402
from omni_parse_bench.harness import contract, errors  # noqa: E402
from omni_parse_bench.harness.providers import (  # noqa: E402
    datalab,
    extend,
    llamaparse,
    llm,
    mistral,
    tesseract,
)


@pytest.mark.parametrize("cls", list(harness.ADAPTERS.values()), ids=list(harness.ADAPTERS))
def test_every_adapter_is_a_page_adapter(cls):
    assert dataclasses.is_dataclass(cls) and issubclass(cls, harness.Parser)
    assert cls.SUPPORTS and cls.SUPPORTS <= {"html", "markdown", "blocks"}
    assert cls().requests(cls.SUPPORTS), "every adapter asks for something"


def test_datalab_asks_one_call_with_headers_kept():
    (r,) = datalab.Datalab().requests(frozenset({"html", "blocks"}))
    assert sorted(r.outputs) == ["blocks", "html"] and r.sent["output_format"] == "html,chunks"
    assert r.sent["additional_config"]["keep_pageheader_in_output"] is True


def test_datalab_gives_markdown_and_leaves_headers_out_when_asked():
    (r,) = datalab.Datalab(headers_footers=False).requests(frozenset({"markdown"}))
    assert r.sent["output_format"] == "markdown"
    assert r.sent["additional_config"] == {"keep_pageheader_in_output": False,
                                           "keep_pagefooter_in_output": False}
    assert datalab.parse({"markdown": "# T", "html": "<h1>T</h1>"}, r) == ({"markdown": "# T"}, {})


def test_an_unknown_option_is_refused_by_name():
    with pytest.raises(ValueError, match="mode"):
        harness.system("datalab", {"mdoe": "fast"})


@dataclasses.dataclass(frozen=True)
class Stub(harness.Parser):
    """A system producing html only, in one call, answering with whatever `ANSWER[0]` returns."""

    SUPPORTS: ClassVar[frozenset[str]] = frozenset({"html"})
    retries: ClassVar[int] = 0

    def requests(self, wants):
        return [contract.Request(frozenset({o}), {}) for o in sorted(wants)]

    def send(self, page, request, *, timeout):
        with core.reading("the stub's answer"):
            return ANSWER[0]()

    def parse(self, raw, request):
        return {o: raw[o] for o in request.outputs}, {}


ANSWER = {0: lambda: contract.Call({"html": "<p>alpha beta</p>"}, cost=contract.Cost(usd=0.01))}


def test_opb_providers_lists_an_adapters_options(capsys):
    from omni_parse_bench import cli

    assert cli.main(["systems", "datalab"]) == 0
    assert "datalab" in capsys.readouterr().out


def test_tesseract_writes_its_text_as_escaped_html():
    r = tesseract.Tesseract().requests(frozenset({"html", "blocks"}))
    assert [sorted(x.outputs) for x in r] == [["html"]]
    outs, errs = tesseract.parse({"text": "a < b & c"}, r[0])
    assert outs == {"html": "<pre>a &lt; b &amp; c</pre>"}
    assert errs == {}


def test_tesseract_output_that_isnt_utf8_is_decoded_not_a_crash():
    import sys

    from omni_parse_bench.harness import budget

    bad = ("import sys; sys.stdout.buffer.write(b'ok \\xff'); sys.stderr.buffer.write(b'no \\xfe'); "
           "sys.exit(1)")
    clock = budget.Budget(60)
    assert tesseract.run([sys.executable, "-c", bad], clock, check=False).stdout == "ok \ufffd"
    with pytest.raises(errors.SystemFailed, match="tesseract exited 1: no \ufffd"):
        tesseract.run([sys.executable, "-c", bad], clock)


def test_tesseract_is_free_and_says_so(monkeypatch, tmp_path):
    import subprocess

    monkeypatch.setattr(tesseract.shutil, "which", lambda _: "/bin/tesseract")
    answered = lambda cmd, deadline, check=True: subprocess.CompletedProcess(cmd, 0, "hi", "")  # noqa: E731
    monkeypatch.setattr(tesseract, "run", answered)
    monkeypatch.setattr(tesseract, "version", lambda: "tesseract 5")
    [r] = tesseract.Tesseract(model="eng").requests(frozenset({"html"}))
    got = tesseract.call(tmp_path / "p.png", r, config=tesseract.Tesseract(model="eng"))
    assert got.cost.usd == 0.0 and got.raw["text"] == "hi"


def test_a_timeout_is_printed_with_its_decimals():
    from omni_parse_bench.harness import budget

    clock = budget.Budget(0.1)
    while not clock.expired(): pass
    with pytest.raises(errors.SystemTimeout, match="the 0.1 s limit"):
        clock.check("the job")


def test_mistral_puts_tables_in_place_and_headers_back():
    r, = mistral.Mistral().requests(mistral.SUPPORTS)
    page = {"markdown": "# Title\n\n![img-0.jpeg](img-0.jpeg)\n\n[tbl-0.html](tbl-0.html)",
            "header": "Journal 12", "footer": "3",
            "tables": [{"id": "tbl-0.html", "content": "<table><tr><td>a</td></tr></table>"}],
            "dimensions": {"width": 200, "height": 100},
            "blocks": [{"type": "table", "top_left_x": 20, "top_left_y": 10, "bottom_right_x": 100,
                        "bottom_right_y": 50, "content": "<table><tr><td>a</td></tr></table>"}]}
    outs, errs = mistral.parse({"pages": [page]}, r)
    assert errs == {}
    assert "Journal 12" in outs["html"] and "<td>a</td>" in outs["html"]
    assert "tbl-0" not in outs["html"] and "img-0" not in outs["html"]
    assert outs["blocks"] == [{"label": "table", "bbox": [0.1, 0.1, 0.5, 0.5], "text": "a"}]


def test_an_answer_that_doesnt_parse_is_recorded(tmp_path, monkeypatch):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    monkeypatch.setitem(ANSWER, 0, lambda: json.loads("<html>"))
    r = core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))
    assert r["output"] is None and "JSONDecodeError" in r["error"]["message"]
    assert r["cost"]["attempts"] == 1


@pytest.mark.parametrize("exc, kind", [("ConnectError", "SystemUnreachable"),
                                       ("ReadError", "SystemUnreachable"),
                                       ("ReadTimeout", "SystemTimeout")])
def test_a_transport_failure_is_the_pages_failure_with_its_cause(tmp_path, monkeypatch, exc, kind):
    import httpx

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")

    def fails():
        raise getattr(httpx, exc)("the network went away")

    monkeypatch.setitem(ANSWER, 0, fails)
    r = core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))
    assert r["error"]["type"] == kind and f"httpx.{exc}: the network went away" in r["error"]["traceback"], r


def test_a_refused_connection_stops_the_run(tmp_path, monkeypatch):
    import httpx

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")

    def refused():
        raise httpx.ConnectError("refused") from ConnectionRefusedError(61, "Connection refused")

    monkeypatch.setitem(ANSWER, 0, refused)
    with pytest.raises(httpx.ConnectError) as got:      # raised as it is, with a note saying how to start it
        core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))
    assert errors.refused(got.value), "the refusal stays in the chain"
    assert any("the connection was refused" in n for n in got.value.__notes__), got.value.__notes__


def test_a_failure_that_is_the_accounts_stops_the_run(tmp_path, monkeypatch):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")

    def refused():
        raise errors.SystemFailed("invalid key", status=401)

    monkeypatch.setitem(ANSWER, 0, refused)
    with pytest.raises(PermissionError):
        core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))


def test_a_saved_answer_is_read_again_without_a_call(tmp_path):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    x = harness.Input(pdf, frozenset({"html"}))
    r = core.predict(Stub(), x)
    assert r["output"] == {"pages": [{"html": "<p>alpha beta</p>"}]} and r["cost"]["usd"] == 0.01
    assert core.reread(Stub(), x, r | {"output": None})["output"] == r["output"]



def pdf(path, texts):
    """A PDF with one page per text, each page's text layer that text, written out by hand."""
    font = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>", None, font]
    kids = []
    for t in texts:
        stream = f"BT /F1 12 Tf 20 50 Td ({t}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
        objs.append(b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 100] "
                    b"/Resources << /Font << /F1 3 0 R >> >> /Contents %d 0 R >>" % len(objs))
        kids.append(len(objs))
    objs[1] = b"<< /Type /Pages /Kids [%s] /Count %d >>" % (b" ".join(b"%d 0 R" % k for k in kids), len(kids))
    out, offsets = bytearray(b"%PDF-1.4\n"), []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n%s\nendobj\n" % (i, o)
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % x for x in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    path.write_bytes(bytes(out))
    return path


def text(page):
    """A one-page PDF's text layer."""
    import pypdfium2 as pdfium

    doc = pdfium.PdfDocument(page)
    try:
        assert len(doc) == 1
        return doc[0].get_textpage().get_text_range().strip()
    finally:
        doc.close()


@dataclasses.dataclass(frozen=True)
class Reads(Stub):
    """The stub, answering with its page's own text; a page whose text is "bad" is a failed call."""

    def send(self, page, request, *, timeout):
        said = text(page)
        if said == "bad":
            raise errors.SystemFailed("the vendor refused this page", status=400)
        return contract.Call({"html": f"<p>{said}</p>"}, cost=contract.Cost(usd=0.01))


def test_a_document_is_parsed_page_by_page_in_order_and_fails_whole(tmp_path):
    x = harness.Input(pdf(tmp_path / "doc.pdf", ["one", "two", "three"]), frozenset({"html"}))
    r = core.predict(Reads(), x)
    assert r["output"] == {"pages": [{"html": f"<p>{t}</p>"} for t in ("one", "two", "three")]}
    assert r["cost"]["usd"] == 0.03 and len(r["raw"]) == 3, r  # one list of answers per page
    # each page is sent as a one-page file, its text layer copied with it
    assert [text(p) for p in harness.raster.pages(x.doc, tmp_path)] == ["one", "two", "three"]
    # read again with no call, as a run's is
    assert core.reread(Reads(), x, r | {"output": None})["output"] == r["output"]
    # a page that fails fails the document, with what the pages before it cost
    bad_doc = pdf(tmp_path / "bad.pdf", ["one", "bad", "three"])
    bad = core.predict(Reads(), harness.Input(bad_doc, frozenset({"html"})))
    assert bad["output"] is None and bad["error"]["message"] == "the vendor refused this page"
    assert bad["cost"]["usd"] == 0.01, bad


def test_an_image_is_a_document_of_one_page_and_a_page_is_never_read_as_its_first_page(tmp_path):
    (png := tmp_path / "p.png").write_bytes(b"png")
    assert harness.raster.pages(png, tmp_path) == [png]
    with pytest.raises(ValueError, match="has 2 pages; a page is one: split it with raster.pages"):
        harness.raster.render(pdf(tmp_path / "two.pdf", ["a", "b"]), lambda size: 1.0)


def test_a_parse_that_raises_a_bug_keeps_the_answer_unread(tmp_path, monkeypatch):
    """A KeyError in `parse` is a bug, not the system's failure: it doesn't fail the page, and the answer is
    kept, unread, for the fixed `parse` to read."""
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    monkeypatch.setitem(ANSWER, 0, lambda: contract.Call({"text": "alpha"}))
    with pytest.raises(KeyError) as got:       # parse's own exception, carrying the record to save
        core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))
    r = got.value.unread
    assert (r["output"], r["error"], r["unread"]) == (None, None, True)
    assert r["raw"][0][0]["raw"] == {"text": "alpha"}


def test_a_parse_raising_system_failed_is_recorded_as_unreadable(tmp_path, monkeypatch):
    """`parse` raising `SystemFailed` on purpose: the page fails, and the record says where, and keeps the
    answer to read again."""
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")

    def parse(self, raw, request):
        raise errors.SystemFailed("no page in the answer", status=200)

    monkeypatch.setattr(Stub, "parse", parse)
    r = core.predict(Stub(), harness.Input(pdf, frozenset({"html"})))
    assert r["output"] is None and r["error"]["type"] == "Unreadable", r
    assert "no page in the answer" in r["error"]["message"] and "in parse" in r["error"]["traceback"]
    assert r["raw"][0][0]["raw"] == {"html": "<p>alpha beta</p>"}


@pytest.mark.parametrize("name, key", [("datalab", "DATALAB_API_KEY"), ("reducto", "REDUCTO_API_KEY"),
                                       ("extend", "EXTEND_API_KEY"), ("llamaparse", "LLAMA_CLOUD_API_KEY"),
                                       ("azure", "AZURE_CU_KEY"), ("mistral", "MISTRAL_API_KEY"),
                                       ("openai/gpt-5.6-sol", "OPENROUTER_API_KEY")])
def test_every_vendor_declares_its_key(name, key, monkeypatch):
    for k in (key, "OPENAI_API_KEY"): monkeypatch.delenv(k, raising=False)
    assert harness.system(name).missing_keys() == [key]
    monkeypatch.setenv(key, "x")
    assert harness.system(name).missing_keys() == []


def test_an_llm_needs_no_openrouter_key_elsewhere_or_with_an_openai_key(monkeypatch):
    for k in ("OPENROUTER_API_KEY", "OPENAI_API_KEY"): monkeypatch.delenv(k, raising=False)
    assert harness.system("openai/gpt-5.6-sol", {"base_url": "http://localhost:8000/v1"}).missing_keys() == []
    monkeypatch.setenv("OPENAI_API_KEY", "x")
    assert harness.system("openai/gpt-5.6-sol").missing_keys() == []


def test_an_option_without_help_of_its_own_has_the_shared_help():
    from omni_parse_bench.harness import adapter

    for name in (*harness.PROVIDERS, "openai/gpt-5.6-sol"):
        for f in dataclasses.fields(harness.adapter_class(name)):
            assert adapter.option_help(f), (name, f.name)


def test_an_llm_reply_cut_off_every_time_is_asked_for_attempts_times_only(tmp_path, monkeypatch):
    import time

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    completions = []

    class Completions:
        def create(self, **kwargs):
            completions.append(1)
            return types.SimpleNamespace(model_dump=lambda: {"choices": [{"finish_reason": "error"}]})

    class Client:
        def __init__(self, **kwargs):
            self.chat = types.SimpleNamespace(completions=Completions())

    monkeypatch.setenv("OPENROUTER_API_KEY", "test")
    monkeypatch.setattr(llm.openai, "OpenAI", Client)
    monkeypatch.setattr(llm, "image", lambda p: b"png")
    monkeypatch.setattr(time, "sleep", lambda s: None)
    r = core.predict(harness.system("org/model"), harness.Input(pdf, frozenset({"html"})))
    assert len(completions) == llm.LLM(model="org/model").attempts
    assert r["output"] is None and r["cost"]["attempts"] == 1


def test_a_request_timeout_never_outlasts_the_budget():
    from omni_parse_bench.harness import budget

    assert budget.Budget(1000).timeout(120) == 120
    assert 0 < budget.Budget(5).timeout(120) <= 5
    assert budget.Budget(0).timeout(120) == 1.0


@pytest.mark.parametrize("reply, html", [
    (CODE_PAGE := "<h1>T</h1>\n<pre>\n```\nprint(1)\n```\n</pre>\n<p>After</p>", CODE_PAGE),
    ("Here is the HTML transcription:\n<h1>T</h1><p>x</p>", "<h1>T</h1><p>x</p>"),
    ("Sure.\n```html\n<h1>T</h1>\n```\nLet me know if you need more.", "<h1>T</h1>"),
    ("<think>first <p>no</p></think>\n<h1>T</h1>", "<h1>T</h1>"),
])
def test_an_llm_html_reply_is_the_page_alone(reply, html):
    assert llm.as_html(reply) == html


@pytest.mark.parametrize("reply", [
    '[{"type": "text", "bbox_2d": [1, 2, 3, 4], "text": "a"},'
    ' {"type": "table", "box_2d": [5, 6, 7, 8], "text": "b"}]',
    '{\n  "type": "text",\n  "bbox_2d": [1, 2, 3, 4],\n  "text": "a"\n}\n'
    '{"type": "table", "bbox_2d": [5, 6, 7, 8], "text": "b"}',
])
def test_an_llm_layout_reply_is_read_as_an_array_or_spread_over_lines(reply):
    assert [(b["label"], b["text"]) for b in llm.as_blocks(reply)] == [("text", "a"), ("table", "b")]


def test_an_extend_block_with_a_null_side_costs_only_that_block():
    page = {"number": 1, "width": 100, "height": 100}
    blocks = [{"type": "text", "content": "a", "metadata": {"page": page},
               "boundingBox": {"left": 0, "top": 0, "right": 10, "bottom": 10}},
              {"type": "figure", "content": "", "metadata": {"page": page},
               "boundingBox": {"left": None, "top": None, "right": None, "bottom": None}}]
    assert [b["text"] for b in extend.layout_blocks(blocks)] == ["a"]


def test_a_llamaparse_item_nested_in_another_gives_its_own_box():
    child = {"type": "text", "md": "Mix well", "bbox": [{"x": 10, "y": 60, "w": 30, "h": 5}]}
    page = {"page_width": 100, "page_height": 100,
            "items": [{"type": "list", "md": "- Mix well", "items": [child]},
                      {"type": "text", "md": "After", "bbox": [{"x": 10, "y": 80, "w": 30, "h": 5}]}]}
    assert [(b["label"], b["text"], b["bbox"][1]) for b in llamaparse.layout_blocks(page)] == [
        ("text", "Mix well", 0.6), ("text", "After", 0.8)]


def test_a_llamaparse_page_that_failed_is_an_error_not_an_empty_page():
    raw = {"markdown": {"pages": [{"page_number": 1, "success": False, "error": "timeout"}]}}
    with pytest.raises(errors.SystemFailed, match="timeout"):
        llamaparse.parse(raw, contract.Request(frozenset({"html"}), {}))


LIGHTON_REPLY = """![header](40,20,960,40)
Annual report

![title](80,70,920,140)
# Company report 2025

![text](80,175,920,225) Revenue rose **20%**.

![text+](80,230,920,260)
It held.

![chart](540,285,920,545)
<table><tr><th>Year</th><th>Revenue</th></tr><tr><td>2025</td><td>€12M</td></tr></table>
"""


def test_a_lighton_reply_is_read_as_its_blocks_and_their_markdown():
    from omni_parse_bench.harness.providers import lighton

    request = lighton.LightOn().requests(frozenset({"html", "blocks"}))[0]
    completion = {"choices": [{"finish_reason": "stop", "message": {"content": LIGHTON_REPLY}}]}
    out, errs = lighton.parse({"completion": completion, "text": LIGHTON_REPLY}, request)
    assert errs == {}
    assert [(b["label"], b["text"]) for b in out["blocks"]] == [
        ("page_furniture", "Annual report"), ("heading", "Company report 2025"),
        ("text", "Revenue rose 20%."), ("text", "It held."), ("figure", "Year Revenue 2025 €12M")]
    assert out["blocks"][1]["bbox"] == [0.08, 0.07, 0.92, 0.14]
    assert "<h1>Company report 2025</h1>" in out["html"] and "<table" not in out["html"]
    assert '<img alt="Year Revenue 2025 €12M">' in out["html"]
    assert "![" not in out["html"]


def test_a_lighton_reply_without_placeholders_is_one_unlabelled_block():
    from omni_parse_bench.harness.providers import lighton

    assert lighton.split("# Just text") == [("", (), "# Just text")]


def test_a_run_is_graded_against_the_dataset_commit_it_ran_on():
    from omni_parse_bench import cli

    said = {"dataset": "hf://datasets/datalab-to/omni_parse_bench", "dataset_commit": "abc123",
            "manifest": "m.parquet"}
    assert cli.recorded(said) == ("hf://datasets/datalab-to/omni_parse_bench@abc123", "m.parquet")
    assert cli.recorded(said, "other") == ("other", "m.parquet")  # a dataset given is graded as given
