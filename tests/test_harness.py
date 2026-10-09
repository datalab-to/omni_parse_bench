"""The adapter contract, and predict and the benchmark loop over a stub vendor (no network)."""
from __future__ import annotations

import dataclasses
import json
import sys
import types

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_parse_bench import benchmark, harness  # noqa: E402
from omni_parse_bench.harness import contract, errors, page, registry  # noqa: E402
from omni_parse_bench.harness.providers import (  # noqa: E402
    azure, datalab, extend, llamaparse, llm, mistral, reducto, tesseract)


ADAPTERS = [datalab, llm, reducto, extend, llamaparse, azure, tesseract, mistral]


@pytest.mark.parametrize("api", ADAPTERS)
def test_every_adapter_has_the_contract(api):
    assert dataclasses.is_dataclass(api.Config)
    assert api.SUPPORTS <= {"html", "blocks"}
    assert callable(api.requests) and callable(api.call) and callable(api.parse)


def test_datalab_asks_one_call_with_headers_kept():
    (r,) = datalab.requests(frozenset({"html", "blocks"}), datalab.Config())
    assert sorted(r.outputs) == ["blocks", "html"] and r.sent["output_format"] == "html,chunks"
    assert r.sent["additional_config"]["keep_pageheader_in_output"] is True


def test_an_unknown_option_is_refused_by_name():
    with pytest.raises(ValueError, match="mode"):
        registry.config_for("datalab", {"mdoe": "fast"})


def stub(fail: set[str] = frozenset()) -> types.ModuleType:
    """A vendor producing html only, one call per output, failing the outputs in `fail`."""
    m = types.ModuleType("stub")

    @dataclasses.dataclass(frozen=True)
    class Config:
        pass

    m.Config, m.SUPPORTS = Config, frozenset({"html"})
    m.requests = lambda wants, config: [contract.Request(frozenset({o}), {}) for o in sorted(wants)]

    def call(p, request, *, timeout, config):
        if request.outputs & fail: raise errors.VendorError("bad request", status=400)
        return contract.Call({"html": "<p>alpha beta</p>"}, cost=contract.Cost(usd=0.01))

    m.call = call
    m.parse = lambda raw, request, config: ({o: raw[o] for o in request.outputs}, {})
    return m


def test_predict_records_unsupported_and_failed_outputs(tmp_path, monkeypatch):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    for m in (page, registry): monkeypatch.setattr(m, "adapter", lambda provider: stub())
    r = harness.predict("stub", pdf, {"html", "blocks"})
    assert r["outputs"] == {"html": "<p>alpha beta</p>"} and r["errors"] == {"blocks": "unsupported"}
    for m in (page, registry): monkeypatch.setattr(m, "adapter", lambda provider: stub(fail={"html"}))
    r = harness.predict("stub", pdf, {"html"})
    assert r["outputs"] == {"html": None} and "bad request" in r["errors"]["html"]


def test_benchmark_predicts_grades_and_resumes(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    data = tmp_path / "dataset"
    (data / "gold").mkdir(parents=True)
    (data / "pages").mkdir()
    (data / "pages" / "a-p1.pdf").write_bytes(b"%PDF")
    tests = [{"id": "t1", "test_type": "present", "output_type": "html", "derivation": "authored", "tags": [],
              "args": {"content": {"text": "alpha", "max_diffs": 0}}, "settings": {}},
             {"id": "t2", "test_type": "layout_kind", "output_type": "blocks", "derivation": "text_layer",
              "tags": [], "args": {"content": {"text": "alpha", "max_diffs": 0, "place": [[0, 0, 1, 1]]}},
              "settings": {"kind": "text"}}]
    (data / "gold" / "a-p1.json").write_text(json.dumps({"tests": tests}))
    row = {"page_id": "a-p1", "document": "a", "suite": "a", "doc_path": "pages/a-p1.pdf",
           "gt_path": "gold/a-p1.json"}
    pq.write_table(pa.Table.from_pylist([row]), data / "manifest.parquet")
    module = stub()
    monkeypatch.setattr(page, "adapter", lambda provider: module)
    monkeypatch.setattr(registry, "adapter", lambda provider: module)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=str(data))
    summaries = benchmark.execute(p, say=lambda s: None)
    (s,) = summaries.values()
    assert s["html"]["score"] == 1.0 and "blocks" not in s and s["pages"] == 1
    (run,) = p.runs
    assert json.loads((run.predictions / "a-p1.json").read_text()) == {"html": "<p>alpha beta</p>"}
    calls = []
    monkeypatch.setattr(module, "call", lambda *a, **k: calls.append(1))
    benchmark.execute(p, say=lambda s: None)
    assert not calls, "a recorded page is not predicted again"


def test_opb_providers_lists_an_adapters_options(capsys):
    from omni_parse_bench import cli

    assert cli.main(["providers", "datalab"]) == 0
    assert "datalab" in capsys.readouterr().out


@pytest.mark.parametrize("argv, module, extra", [
    (["providers"], "rich", "harness"),
    (["tests", "--dataset", "hf://datasets/x/y"], "huggingface_hub", "benchmark"),
])
def test_opb_names_the_extra_a_core_install_lacks(monkeypatch, capsys, argv, module, extra):
    """On an install without the command's extra, opb says which extra to add, not a traceback."""
    from omni_parse_bench import cli

    monkeypatch.setitem(sys.modules, module, None)   # importing it now raises ImportError
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert f"opb {argv[0]} needs {module}" in err and f"pip install 'omni-parse-bench[{extra}]'" in err


def test_tesseract_writes_its_text_as_escaped_html():
    r = tesseract.requests(frozenset({"html", "blocks"}), tesseract.Config())
    assert [sorted(x.outputs) for x in r] == [["html"]]
    outs, errs = tesseract.parse({"text": "a < b & c"}, r[0])
    assert outs == {"html": "<pre>a &lt; b &amp; c</pre>"}
    assert errs == {}


def test_mistral_puts_tables_in_place_and_headers_back():
    r, = mistral.requests(mistral.SUPPORTS, mistral.Config())
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



def dataset(root, n: int = 1) -> str:
    """A dataset of `n` one-test pages, each passing when its html holds "alpha"."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    (root / "gold").mkdir(parents=True)
    (root / "pages").mkdir()
    rows = []
    for i in range(n):
        pid = f"a-p{i}"
        (root / "pages" / f"{pid}.pdf").write_bytes(b"%PDF")
        t = {"id": f"t{i}", "test_type": "present", "output_type": "html", "derivation": "authored",
             "tags": [], "args": {"content": {"text": "alpha", "max_diffs": 0}}, "settings": {}}
        (root / "gold" / f"{pid}.json").write_text(json.dumps({"tests": [t]}))
        rows.append({"page_id": pid, "document": "a", "suite": "a", "doc_path": f"pages/{pid}.pdf",
                     "gt_path": f"gold/{pid}.json"})
    pq.write_table(pa.Table.from_pylist(rows), root / "manifest.parquet")
    return str(root)


def use(monkeypatch, modules: dict[str, types.ModuleType]) -> None:
    for m in (page, registry): monkeypatch.setattr(m, "adapter", lambda provider: modules[provider])


def test_a_page_predicted_again_is_graded_again(tmp_path, monkeypatch):
    module = stub()
    use(monkeypatch, {"stub": module})
    answers = iter([errors.VendorTimeout("slow"), contract.Call({"html": "<p>alpha</p>"})])

    def call(*a, **k):
        if isinstance(got := next(answers), Exception): raise got
        return got

    monkeypatch.setattr(module, "call", call)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    (s,) = benchmark.execute(p, say=lambda s: None).values()
    assert s["html"]["score"] == 0.0
    (s,) = benchmark.execute(p._replace(retry_failed=True), say=lambda s: None).values()
    assert s["html"]["score"] == 1.0, "the new record's verdict, not the one graded before"


def test_an_interrupt_stops_every_run(tmp_path, monkeypatch):
    import time

    a, b, calls = stub(), stub(), []

    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt

    def slow(*args, **kwargs):
        calls.append(1)
        time.sleep(0.05)
        return contract.Call({"html": "<p>alpha</p>"})

    monkeypatch.setattr(a, "call", interrupted)
    monkeypatch.setattr(b, "call", slow)
    use(monkeypatch, {"a": a, "b": b})
    p = benchmark.plan(["a", "b"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 60), workers=2)
    with pytest.raises(KeyboardInterrupt):
        benchmark.execute(p, say=lambda s: None)
    assert len(calls) < 10, f"run b went on after the interrupt: {len(calls)} of 60 pages"


def test_the_same_run_twice_is_refused():
    for providers, options in ((["datalab", "datalab"], None),
                               (["datalab"], {"datalab": [{"mode": "accurate"}, {}]})):
        with pytest.raises(ValueError, match="more than once"):
            benchmark.plan(providers, options=options, dataset="unused")


def test_an_answer_that_doesnt_parse_is_recorded(tmp_path, monkeypatch):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    module = stub()
    use(monkeypatch, {"stub": module})

    def call(*a, **k):
        return json.loads("<html>")

    monkeypatch.setattr(module, "call", call)
    r = harness.predict("stub", pdf, {"html"})
    assert r["outputs"] == {"html": None} and "JSONDecodeError" in r["errors"]["html"]
    assert r["calls"][0]["attempts"] == 1


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
    r = harness.predict("org/model", pdf, {"html"})
    assert len(completions) == llm.Config(model="org/model").attempts
    assert r["outputs"] == {"html": None} and r["calls"][0]["attempts"] == 1


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
    with pytest.raises(errors.VendorError, match="timeout"):
        llamaparse.parse(raw, contract.Request(frozenset({"html"}), {}))
