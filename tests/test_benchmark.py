"""The benchmark loop over stub vendors (no network): concurrency per adapter, what a resume predicts
and grades again, a run's dataset, and the CLI's exit codes."""
from __future__ import annotations

import argparse
import ast
import dataclasses
import json
import logging
import pathlib
import threading
import time
import types

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

import httpx  # noqa: E402

from omni_parse_bench import benchmark, cli, data, harness  # noqa: E402
from omni_parse_bench.scorers.unit_tests import tests as gold  # noqa: E402
from omni_parse_bench.scorers import unit_tests as scorer  # noqa: E402
from omni_parse_bench.harness import budget, contract, errors, page, registry  # noqa: E402
from omni_parse_bench.harness.providers import azure, extend, reducto  # noqa: E402

QUIET = lambda s: None  # noqa: E731
PROVIDERS = pathlib.Path(benchmark.__file__).parent / "harness" / "providers"
CREDENTIALS = {"DATALAB_API_KEY", "REDUCTO_API_KEY", "EXTEND_API_KEY", "EXTEND_WORKSPACE_ID",
               "LLAMA_CLOUD_API_KEY", "MISTRAL_API_KEY", "OPENROUTER_API_KEY", "OPB_ENDPOINT_KEY",
               "OPENAI_API_KEY", "AZURE_CU_KEY"}


def stub(name: str = "stub", call=None, supports=frozenset({"html"})) -> types.ModuleType:
    """A vendor named `name`, with a `tier` option, one call per output; `call(config)` answers."""
    m = types.ModuleType(name)

    @dataclasses.dataclass(frozen=True)
    class Config:
        tier: str = "top"

    m.Config, m.SUPPORTS = Config, frozenset(supports)
    m.requests = lambda wants, config: [contract.Request(frozenset({o}), {}) for o in sorted(wants)]

    def default(config):
        return contract.Call({"html": "<p>alpha</p>"}, cost=contract.Cost(usd=0.01))

    def answer(p, request, *, timeout, config):
        got = (call or default)(config)
        if isinstance(got, BaseException): raise got
        return got

    m.call = answer
    m.parse = lambda raw, request, config: ({o: raw[o] for o in request.outputs if o in raw}, {})
    return m


def use(monkeypatch, modules: dict[str, types.ModuleType]) -> None:
    for m in (page, registry): monkeypatch.setattr(m, "adapter", lambda provider: modules[provider])


def dataset(root: pathlib.Path, n: int = 1, blocks: bool = False, outputs: list | None = None,
            extra: dict | None = None) -> str:
    """A dataset of `n` pages, each with an html test passing on "alpha" (and a blocks test); the
    manifest says to predict what the tests read, or `outputs`, and `extra` adds columns."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    (root / "gold").mkdir(parents=True)
    (root / "pages").mkdir()
    rows = []
    for i in range(n):
        pid = f"a-p{i}"
        (root / "pages" / f"{pid}.pdf").write_bytes(b"%PDF " + pid.encode())
        ts = [{"id": f"t{i}", "test_type": "present", "output_type": "html", "derivation": "authored",
               "tags": [], "args": {"content": {"text": "alpha", "max_diffs": 0}}, "settings": {}}]
        if blocks:
            ts.append({"id": f"k{i}", "test_type": "layout_kind", "output_type": "blocks",
                       "derivation": "text_layer", "tags": [],
                       "args": {"content": {"text": "alpha", "max_diffs": 0, "place": [[0, 0, 1, 1]]}},
                       "settings": {"kind": "text"}})
        (root / "gold" / f"{pid}.json").write_text(json.dumps({"tests": ts}))
        wanted = ["html"] + ["blocks"] * blocks if outputs is None else outputs
        rows.append({"page_id": pid, "document": "a", "suite": "a", "doc_path": f"pages/{pid}.pdf",
                     "gt_path": f"gold/{pid}.json", "outputs": wanted} | (extra or {}))
    pq.write_table(pa.Table.from_pylist(rows), root / "manifest.parquet")
    return str(root)


def saved(run: benchmark.Run, pid: str = "a-p0") -> dict:
    return json.loads((run.records / f"{pid}.json").read_text())


# 1. Concurrency per adapter.

def test_runs_of_one_adapter_share_its_cap(tmp_path, monkeypatch):
    lock, now, peak = threading.Lock(), [0], [0]

    def slow(config):
        with lock:
            now[0] += 1
            peak[0] = max(peak[0], now[0])
        time.sleep(0.02)
        with lock: now[0] -= 1
        return contract.Call({"html": "<p>alpha</p>"})

    use(monkeypatch, {"shared": stub("shared", slow)})
    p = benchmark.plan(["shared"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 10),
                       options={"shared": [{"tier": "a"}, {"tier": "b"}]}, workers=2)
    assert len(p.runs) == 2
    benchmark.execute(p, say=QUIET)
    assert peak[0] <= 2, f"two runs of one adapter had {peak[0]} calls out at once, over its cap of 2"
    assert benchmark._workers_for("datalab") == benchmark.WORKERS["datalab"]
    assert benchmark._workers_for("datalab", 3) == 3 and benchmark._workers_for("unknown") == 5


def test_workers_may_be_set_per_adapter(tmp_path, monkeypatch):
    """Per adapter, the vendor account the limit is: a model id is refused, naming its adapter."""
    assert benchmark._per_adapter({"datalab": 20, "llm": 3}) == {"datalab": 20, "llm": 3}
    assert benchmark._workers_for("reducto", {"datalab": 20}) == benchmark.WORKERS["reducto"]
    for bad, why in [({"nope": 2}, "the adapters are"), ({"openai/gpt-5.6-sol": 3}, 'write {"llm": 3}'),
                     ({"datalab": 0}, "1 or more"), ({"datalab": True}, "1 or more")]:
        with pytest.raises(ValueError, match=why):
            benchmark._per_adapter(bad)
    assert cli.read_workers("8") == 8 and cli.read_workers('{"datalab": 20}') == {"datalab": 20}
    with pytest.raises(argparse.ArgumentTypeError):
        cli.read_workers("abc")
    use(monkeypatch, {"shared": stub("shared")})
    p = benchmark.plan(["shared"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"),
                       workers={"tesseract": 7})
    assert p.workers == {"tesseract": 7} and benchmark._workers_for("tesseract", p.workers) == 7


# 2. An account failure stops its adapter's runs, and only those.

def test_an_account_failure_stops_every_run_of_its_adapter_only(tmp_path, monkeypatch, caplog):
    calls = {"a-ok": 0, "b": 0}

    def a(config):
        if config.tier == "broke": return errors.VendorError("payment required", status=402)
        calls["a-ok"] += 1
        time.sleep(0.02)
        return contract.Call({"html": "<p>alpha</p>"})

    def b(config):
        calls["b"] += 1
        return contract.Call({"html": "<p>alpha</p>"})

    use(monkeypatch, {"a": stub("a", a), "b": stub("b", b)})
    p = benchmark.plan(["a", "b"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 30),
                       options={"a": [{"tier": "broke"}, {"tier": "ok"}]}, workers=2)
    with caplog.at_level(logging.ERROR, logger="omni_parse_bench.benchmark"), \
            pytest.raises(errors.AccountFailure):
        benchmark.execute(p, say=QUIET)
    assert calls["a-ok"] < 5, f"the other run of the failed adapter went on: {calls['a-ok']} of 30 pages"
    assert calls["b"] == 30, "another adapter's run is stopped by this one's account"
    assert any("stopped its runs" in m for m in caplog.messages)


# 3. --retry-failed asks again only what may go otherwise.

@pytest.mark.parametrize("failure, error, again", [
    ({"class": "VendorError", "status": 400}, "VendorError: HTTP 400", False),
    ({"class": "VendorError", "status": 200}, "VendorError: parse run FAILED", False),
    ({"class": "VendorError", "status": 200}, "VendorError: the reply hit max_output_tokens", False),
    ({"class": "VendorError", "status": 503}, "VendorError: HTTP 503", True),
    ({"class": "VendorError", "status": 522}, "VendorError: HTTP 522", True),
    ({"class": "VendorError", "status": None}, "VendorError: polling failed", True),
    ({"class": "VendorTimeout", "status": None}, "VendorTimeout: timed out", True),
    ({"class": "VendorUnreachable", "status": None}, "VendorUnreachable: reset", True),
    (None, "VendorTimeout: timed out", False),      # a call without a failure got an answer
    (None, "the adapter couldn't read the answer: KeyError", False),
])
def test_retry_failed_asks_again_only_what_may_go_otherwise(failure, error, again):
    rec = {"outputs": {"html": None}, "errors": {"html": error},
           "calls": [{"outputs": ["html"]} | ({"failure": failure} if failure else {})]}
    want = frozenset({"html"})
    assert benchmark._missing(rec, want) == frozenset()
    assert benchmark._missing(rec, want, retry_failed=True) == (want if again else frozenset())


# 4. A run's dataset, gold and timeout.

def test_a_loop_of_ones_own_keeps_a_run_through_its_functions(tmp_path, monkeypatch):
    """prepare, needs, record and recorded: predict_all's bookkeeping, for a loop that predicts elsewhere."""
    monkeypatch.setattr(data, "read_manifest", lambda d, m=data.MANIFEST: (tmp_path / "gold-1", ()))
    r = benchmark.Run("tesseract", {}, tmp_path / "run")
    benchmark.prepare(r, "some/dataset", 900.0)
    settings = json.loads((r.out / "settings.json").read_text())
    assert settings["timeout_s"] == 900.0 and "gold" not in settings, "grade writes the gold it graded with"
    page = data.Page("p1", "d1", "suite", "pages/p1.pdf", "gold/p1.json", ("blocks", "html"))
    assert page.id == page.page_id == "p1"
    want = frozenset(page.outputs)
    assert benchmark.needs(r, page) == want
    call = {"outputs": ["html", "blocks"], "usd": 0, "wall_s": 1.0,
            "failure": {"class": "VendorTimeout", "status": None, "transient": True}}
    first = {"outputs": {"html": "<p>a</p>", "blocks": None}, "calls": [call], "raw": [],
             "errors": {"blocks": "VendorTimeout: timed out"}}
    benchmark.record(r, "p1", first)
    assert json.loads((r.predictions / "p1.json").read_text()) == {"html": "<p>a</p>", "blocks": None}
    assert benchmark.needs(r, page) == frozenset()
    assert benchmark.needs(r, page, retry_failed=True) == frozenset({"blocks"})
    again = {"outputs": {"blocks": []}, "errors": {}, "calls": [call], "raw": []}
    kept = benchmark.record(r, "p1", again)
    assert kept["outputs"] == {"html": "<p>a</p>", "blocks": []} and kept["errors"] == {}
    assert len(kept["calls"]) == 2 and benchmark.recorded(r, "p1") == kept


def test_a_run_never_prepared_is_not_graded(tmp_path):
    """Most likely another folder (another option, another --out), so it is refused, not passed over."""
    r = benchmark.Run("tesseract", {}, tmp_path / "nowhere")
    with pytest.raises(ValueError, match="never prepared"):
        benchmark.grade(r, ())


def test_a_hugging_face_dataset_is_downloaded_whole_at_one_revision(tmp_path, monkeypatch):
    """Pages and gold from one download, so they are always one commit's."""
    import huggingface_hub

    got = {}

    def download(repo, **kwargs):
        got.update(kwargs, repo=repo)
        return str(tmp_path / "abc123")

    monkeypatch.setattr(huggingface_hub, "snapshot_download", download)
    assert data.download_dataset("hf://datasets/org/data@main").name == "abc123"
    assert got["repo"] == "org/data" and got["revision"] == "main" and "allow_patterns" not in got


def test_a_run_folder_holds_one_dataset_and_a_changed_gold_grades_its_page_again(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    one, two = dataset(tmp_path / "one"), dataset(tmp_path / "two")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=one, timeout=30)
    (s,) = benchmark.execute(p, say=QUIET).values()
    (run,) = p.runs
    settings = json.loads((run.out / "settings.json").read_text())
    assert settings["dataset"] == data.dataset_id(one) and settings["timeout_s"] == 30
    assert s["scorer"] == benchmark.SCORER and s["html"]["score"] == 1.0
    assert "gold" not in settings, "settings.json says what the run asks; what graded it is on its lines"
    with pytest.raises(ValueError, match="never mixes datasets"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=two)
    gold = pathlib.Path(one) / "gold" / "a-p0.json"
    gold.write_text(gold.read_text().replace('"alpha"', '"beta"'))
    data.read_manifest.cache_clear()
    benchmark._TESTS.clear()
    graded = graded_pages(monkeypatch)
    (s,) = benchmark.execute(benchmark.plan(["stub"], out=tmp_path / "runs", dataset=one), say=QUIET).values()
    assert graded == ["a-p0"] and s["html"]["score"] == 0.0, "the stub still says alpha"


def test_each_call_keeps_the_timeout_it_ran_under(tmp_path, monkeypatch):
    answers = iter([errors.VendorTimeout("slow"), contract.Call({"html": "<p>alpha</p>"})])
    use(monkeypatch, {"stub": stub(call=lambda config: next(answers))})
    ds = dataset(tmp_path / "data")
    benchmark.execute(benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds, timeout=5), say=QUIET)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds, timeout=7, retry_failed=True)
    benchmark.execute(p, say=QUIET)
    rec = saved(p.runs[0])
    assert [c["timeout_s"] for c in rec["calls"]] == [5, 7] and rec["timeout_s"] == 7


def test_a_page_already_answered_is_not_predicted_again(tmp_path, monkeypatch):
    """A run folder assumes its pages don't change, so a resume reads records, not page files."""
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    ds = dataset(tmp_path / "data")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    benchmark.execute(p, say=QUIET)
    (pathlib.Path(ds) / "pages" / "a-p0.pdf").write_bytes(b"%PDF another page")
    benchmark.execute(p, say=QUIET)
    assert len(calls) == 1


def test_a_manifest_that_says_what_to_predict_is_planned_without_the_gold(tmp_path, monkeypatch):
    """With outputs in the manifest, planning and predicting read no gold file; grading does."""
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    ds = dataset(tmp_path / "data", n=2, outputs=["html"])
    assert [p.outputs for p in data.read_manifest(ds)[1]] == [("html",), ("html",)]
    read = []
    real = gold.read
    monkeypatch.setattr(gold, "read", lambda path: read.append(path) or real(path))
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    benchmark.predict_all(p)
    assert len(calls) == 2 and read == [], "planning and predicting read no gold"
    assert benchmark.grade_all(p, say=QUIET)[p.runs[0].out.name]["pages"] == 2 and read


def test_a_dataset_from_before_outputs_says_how_to_get_the_current_one(tmp_path):
    """What this omni-parse-bench meets in a dataset commit made for 0.1.x: the fixes are in the message."""
    import pyarrow.parquet as pq

    ds = dataset(tmp_path / "data")
    table = pq.read_table(pathlib.Path(ds) / "manifest.parquet")
    pq.write_table(table.drop_columns(["outputs"]), pathlib.Path(ds) / "manifest.parquet")
    with pytest.raises(data.ManifestError, match="from before omni-parse-bench 0.1.2") as e:
        data.read_manifest(ds)[1]
    for fix in ("hf://datasets/datalab-to/omni_parse_bench", "hf download datalab-to/omni_parse_bench",
                "pip install 'omni-parse-bench==0.1.1'"):
        assert fix in str(e.value)


def test_outputs_out_of_step_with_the_gold_are_refused(tmp_path):
    ds = dataset(tmp_path / "data", blocks=True, outputs=["html"])
    with pytest.raises(gold.GoldError, match="out of step with the gold"):
        scorer.check(data.read_manifest(ds)[1])


@pytest.mark.parametrize("outputs", [[], ["html", "html"], ["html", "pdf"]])
def test_outputs_must_be_distinct_known_output_types(tmp_path, outputs):
    ds = dataset(tmp_path / "data", outputs=outputs)
    with pytest.raises(data.ManifestError, match="distinct output types"):
        data.read_manifest(ds)[1]


def test_a_manifest_column_of_its_own_is_carried_not_refused(tmp_path, monkeypatch):
    """A dataset may carry columns omni-parse-bench doesn't read (a language, a tag, another gold), for
    scorers of its own: they ride on the page, and the run is the same."""
    ds = dataset(tmp_path / "data", extra={"weight": "1", "language": "tha"})
    (page,) = data.read_manifest(ds)[1]
    assert page.extra == {"weight": "1", "language": "tha"}
    bare = [data.Page("p", "d", "s", "pages/p.pdf", "gold/p.json", ("html",)) for _ in range(2)]
    assert bare[0].extra == {} and bare[0].extra is not bare[1].extra, "each page has its own"
    use(monkeypatch, {"stub": stub()})
    (s,) = benchmark.execute(benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds), say=QUIET).values()
    assert s["html"]["score"] == 1.0


# 5. The plan counts what will be predicted.

def test_the_plan_counts_what_will_be_predicted(tmp_path, monkeypatch):
    answers = iter([errors.VendorTimeout("slow")])
    use(monkeypatch, {"stub": stub(call=lambda config: next(answers))})
    ds = dataset(tmp_path / "data", blocks=True)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    (run,) = p.runs
    assert benchmark.owed(p, run) == (1, 1)
    benchmark.execute(p, say=QUIET)
    assert saved(run)["errors"]["blocks"] == "unsupported"
    # Note: an unsupported output is settled, so nothing is predicted; grading is fresh, so the page is
    # graded.
    assert benchmark.owed(p, run) == (0, 1)
    assert benchmark.owed(p._replace(retry_failed=True), run) == (1, 1)
    assert "predict" in benchmark.describe(p)


# 6. Score lines carry the gold and scorer that graded them.

def test_a_run_graded_by_another_scorer_is_graded_again(tmp_path, monkeypatch):
    """A new scorer grades every page again, no provider called, so a run's lines are one scorer's."""
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    (s,) = benchmark.execute(p, say=QUIET).values()
    (run,) = p.runs
    rows = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert {r["scorer"] for r in rows} == {benchmark.SCORER} and s["scorer"] == benchmark.SCORER
    monkeypatch.setattr(benchmark, "SCORER", "next")
    graded = graded_pages(monkeypatch)
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert graded == ["a-p0", "a-p1"]
    rows = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert {r["scorer"] for r in rows} == {"next"}




def test_a_renamed_test_is_a_gold_change(tmp_path, monkeypatch):
    """Renaming a test changes the gold: its page is graded again, under the new name."""
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    benchmark.execute(p, say=QUIET)
    gold = pathlib.Path(ds) / "gold" / "a-p0.json"
    gold.write_text(gold.read_text().replace('"t0"', '"t0-renamed"'))
    data.read_manifest.cache_clear()
    benchmark._TESTS.clear()
    (s,) = benchmark.execute(p._replace(score_only=True), say=QUIET).values()
    assert s["html"]["score"] == 1.0
    lines = [json.loads(x) for x in (p.runs[0].out / "scores.jsonl").read_text().splitlines()]
    assert [x["test_id"] for x in lines] == ["t0-renamed"]


# 7, 8. The CLI: errors in our code exit 2; scores come with their coverage.

def test_opb_benchmark_exits_2_when_our_code_errored(monkeypatch, capsys):
    clean = {"html": {"score": 0.9}, "pages": 3, "pending": 1}
    for summaries, code in (({"r": clean}, 0), ({"r": clean | {"html": {"score": 0.9, "errors": 2}}}, 2)):
        monkeypatch.setattr(benchmark, "plan", lambda *a, **k: None)
        monkeypatch.setattr(benchmark, "execute", lambda p, say, s=summaries: s)
        assert cli.main(["benchmark", "--providers", "x", "-y"]) == code
        out, err = capsys.readouterr()
        assert json.loads(out) == {"r": {"html": 0.9, "pages": 3, "pending": 1}}
        assert ("warning" in err) == bool(code)


def test_a_score_is_said_with_its_coverage(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    said = []
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 3), limit=2)
    benchmark.execute(p, say=said.append)
    assert "html 100.0 over 2 pages graded, 1 pending" in said[0]


# 9. Adapter fixes.

def mock(monkeypatch, module, handler) -> None:
    """`module`'s httpx clients answer with `handler`, and its waits take no time."""
    real, transport = httpx.Client, httpx.MockTransport(handler)
    monkeypatch.setattr(module.httpx, "Client", lambda **kw: real(transport=transport, **kw))
    monkeypatch.setattr(budget.time, "sleep", lambda s: None)
    monkeypatch.setattr(module.time, "sleep", lambda s: None)


@pytest.mark.parametrize("status, ok", [("COMPLETED", True), ("PROCESSED", True), ("CANCELLED", False),
                                        ("ERROR", False), ("FAILED", False)])
def test_extend_ends_on_every_terminal_status(tmp_path, monkeypatch, status, ok):
    run = {"id": "r", "status": status, "output": {"chunks": [{"content": "alpha", "blocks": []}]}}

    def handler(req):
        if req.url.path.endswith("/files/upload"): return httpx.Response(200, json={"id": "f"})
        if req.method == "POST": return httpx.Response(200, json={"id": "r"})
        return httpx.Response(200, json=run)

    mock(monkeypatch, extend, handler)
    monkeypatch.setenv("EXTEND_API_KEY", "test")
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    rec = harness.predict("extend", pdf, {"html"})
    assert (rec["outputs"]["html"] is not None) == ok
    if not ok:
        assert rec["calls"][0]["failure"]["status"] == 200 and not benchmark._retryable(rec, "html")


@pytest.mark.parametrize("reason, retried", [("INTERNAL_ERROR", True), ("OCR_ERROR", True),
                                             ("CORRUPT_FILE", False)])
def test_an_extend_outage_is_retried_and_a_bad_file_is_not(tmp_path, monkeypatch, reason, retried):
    runs = []

    def handler(req):
        if req.url.path.endswith("/files/upload"): return httpx.Response(200, json={"id": "f"})
        if req.method == "POST":
            runs.append(1)
            return httpx.Response(200, json={"id": "r"})
        return httpx.Response(200, json={"id": "r", "status": "FAILED", "failureReason": reason})

    mock(monkeypatch, extend, handler)
    monkeypatch.setattr(page.time, "sleep", lambda s: None)
    monkeypatch.setenv("EXTEND_API_KEY", "test")
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    rec = harness.predict("extend", pdf, {"html"})
    assert len(runs) == (page.TRANSIENT_ATTEMPTS if retried else 1)
    assert benchmark._retryable(rec, "html") == retried and reason in rec["errors"]["html"]


def test_extend_and_reducto_are_asked_at_their_top_settings():
    sent = extend.requests(frozenset({"html"}), extend.Config())[0].sent["config"]
    assert sent["blockOptions"]["text"]["agentic"] == {"enabled": True}
    assert sent["blockOptions"]["tables"]["agentic"] == {"enabled": True}
    assert sent["advancedOptions"] == {"imageConversionQuality": "high"}
    sent = reducto.requests(frozenset({"html"}), reducto.Config())[0].sent
    assert sent["settings"] == {"model": "r-1"} and "enhance" not in sent
    legacy = reducto.requests(frozenset({"html"}), reducto.Config(model="legacy"))[0].sent
    assert legacy["settings"]["model"] == "legacy" and legacy["enhance"]["agentic"][0]["mode"] == "max"


def test_an_r1_figure_description_is_alt_text_and_a_legacy_figures_words_stay_page_text():
    said = "Bar chart titled \u201cPrice\u201d.\n<verbose>\nX-axis: 2020\n</verbose>"
    blocks = [{"type": "Text", "content": "Body"},
              {"type": "Figure", "content": said, "extra": {"model": "r-1"}},
              {"type": "Figure", "content": "Q3 sales", "extra": {}}]
    raw = {"result": {"result": {"chunks": [{"content": f"# Body\n\n{said}\n\nQ3 sales", "blocks": blocks}]}}}
    page = reducto.parse(raw, contract.Request(frozenset({"html"}), {}))[0]["html"]
    assert "<p>Bar chart" not in page and "<verbose>" not in page and "<p>Q3 sales</p>" in page
    assert 'alt="Bar chart titled \u201cPrice\u201d. &lt;verbose&gt; X-axis: 2020 &lt;/verbose&gt;"' in page


def test_reducto_retries_its_result_url_and_a_403_there_is_not_the_account(tmp_path, monkeypatch):
    stored = iter([httpx.Response(503), httpx.Response(200, json={"chunks": [{"content": "alpha"}]}),
                   httpx.Response(403, text="Request has expired")])
    job = {"status": "Completed", "result": {"result": {"type": "url", "url": "https://store.example/x"}}}

    def handler(req):
        if req.url.host == "store.example": return next(stored)
        if req.url.path == "/upload": return httpx.Response(200, json={"file_id": "f"})
        if req.url.path == "/parse_async": return httpx.Response(200, json={"job_id": "j"})
        return httpx.Response(200, json=json.loads(json.dumps(job)))

    mock(monkeypatch, reducto, handler)
    monkeypatch.setenv("REDUCTO_API_KEY", "test")
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    assert harness.predict("reducto", pdf, {"html"})["outputs"]["html"]
    rec = harness.predict("reducto", pdf, {"html"})
    assert rec["outputs"]["html"] is None and "403" in rec["errors"]["html"]


def test_cloudflare_statuses_are_transient():
    assert {520, 521, 522, 523, 524} <= errors.TRANSIENT_STATUSES


def test_azure_takes_its_endpoint_from_options_not_the_shell(tmp_path, monkeypatch):
    monkeypatch.setenv("AZURE_CU_KEY", "test")
    monkeypatch.setenv("AZURE_CU_ENDPOINT", "https://set-in-the-shell.example")
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    with pytest.raises(errors.MissingCredential, match="endpoint"):
        harness.predict("azure", pdf, {"html"})
    with_var = harness.out_name("azure")
    monkeypatch.delenv("AZURE_CU_ENDPOINT")
    assert harness.out_name("azure") == with_var, "a run's directory is a function of its options"
    assert harness.out_name("azure", {"endpoint": "https://a.example"}) != with_var
    assert azure.Config(endpoint="https://a.example/").endpoint == "https://a.example"


def env_reads(path: pathlib.Path) -> list[tuple[str, int]]:
    """Every `os.environ[...]`, `os.environ.get(...)` and `os.getenv(...)` name in a module, with its line."""
    found = []
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Call) and ast.unparse(node.func).endswith(("environ.get", "getenv")):
            arg = node.args[0] if node.args else None
        elif isinstance(node, ast.Subscript) and "environ" in ast.unparse(node.value):
            arg = node.slice
        else: continue
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            found.append((arg.value, node.lineno))
    return found


def test_no_adapter_reads_a_setting_from_the_environment():
    """A key decides whether a call is allowed, not what it asks; anything that steers a vendor is a
    `Config` field, so it reaches the run's settings and its directory name."""
    modules = sorted(p for p in PROVIDERS.glob("*.py") if p.stem != "__init__")
    assert modules
    bad = [f"{p.name}: {n} (line {line})" for p in modules for n, line in env_reads(p)
           if n not in CREDENTIALS]
    assert not bad, f"adapters must take settings from their Config, not the environment: {bad}"


# 10. Validation.

def test_a_bad_count_or_an_empty_options_list_is_refused():
    for kwargs in ({"limit": -1}, {"sample": -2}, {"workers": -1}):
        with pytest.raises(ValueError, match="negative"):
            benchmark.plan(["datalab"], dataset="unused", **kwargs)
    with pytest.raises(ValueError, match="empty list"):
        benchmark.plan(["datalab"], dataset="unused", options={"datalab": []})
    with pytest.raises(ValueError, match="negative"):
        cli.main(["benchmark", "--providers", "datalab", "--limit", "-1", "-y"])


def test_a_missing_repo_fails_at_once_and_a_network_fault_is_retried(monkeypatch):
    import huggingface_hub
    from huggingface_hub import errors as hf_errors

    sleeps = []
    monkeypatch.setattr(data.time, "sleep", sleeps.append)

    def missing(*a, **k):
        raise hf_errors.RepositoryNotFoundError.__new__(hf_errors.RepositoryNotFoundError)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    with pytest.raises(ValueError, match="RepositoryNotFoundError"):
        data.download_dataset("hf://datasets/org/nothing")
    assert not sleeps
    faults = iter([OSError("reset"), "/tmp/abc"])

    def flaky(*a, **k):
        if isinstance(got := next(faults), Exception): raise got
        return got

    monkeypatch.setattr(huggingface_hub, "snapshot_download", flaky)
    assert data.download_dataset("hf://datasets/org/data").name == "abc" and len(sleeps) == 1


# 11. Unreadable files, and an interrupted grading.

def test_an_unreadable_record_is_predicted_again_and_a_bad_score_line_graded_again(tmp_path, monkeypatch):
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    (run.records / "a-p0.json").write_text("{not json")
    scores = run.out / "scores.jsonl"
    scores.write_text("garbage\n" + scores.read_text().splitlines()[1] + "\n")
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert len(calls) == 3 and s["pages"] == 2 and s["html"]["score"] == 1.0
    assert len(scores.read_text().splitlines()) == 2


def test_every_grading_grades_every_predicted_page_fresh(tmp_path, monkeypatch):
    """No line is reused: a grading's files are always that grading's, whatever was on disk before."""
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data", 2)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    benchmark.execute(p, say=QUIET)
    pages = data.read_manifest(ds)[1]
    graded = graded_pages(monkeypatch)
    benchmark.grade(p.runs[0], pages, say=QUIET)
    benchmark.grade(p.runs[0], pages, say=QUIET)
    assert graded == ["a-p0", "a-p1", "a-p0", "a-p1"]


def test_an_interrupted_grading_writes_nothing(tmp_path, monkeypatch):
    """An interrupted grading leaves the last finished grading's files as they were, so a run's scores
    are always one whole grading's, never a mix of two."""
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 3))
    benchmark.execute(p, say=QUIET)
    path = p.runs[0].out / "scores.jsonl"
    before = path.read_text()
    monkeypatch.setattr(benchmark, "SCORER", "next")
    real, n = benchmark._grade_page, [0]

    def once(*a):
        n[0] += 1
        if n[0] == 2: raise KeyboardInterrupt
        return real(*a)

    monkeypatch.setattr(benchmark, "_grade_page", once)
    with pytest.raises(KeyboardInterrupt):
        benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert path.read_text() == before
    monkeypatch.setattr(benchmark, "_grade_page", real)
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    rows = [json.loads(x) for x in path.read_text().splitlines()]
    assert [r["page_id"] for r in rows] == ["a-p0", "a-p1", "a-p2"]
    assert {r["scorer"] for r in rows} == {"next"}




def test_the_scorer_stamp_changes_with_the_scoring_code(tmp_path, monkeypatch):
    pkg = tmp_path / "omni_parse_bench"
    for name in benchmark.SCORING:
        (pkg / name).parent.mkdir(parents=True, exist_ok=True)
        (pkg / name).write_bytes((benchmark.PACKAGE / name).read_bytes())
    monkeypatch.setattr(benchmark, "PACKAGE", pkg)
    before = benchmark.scorer_version()
    assert before == benchmark.SCORER
    runners = pkg / "scorers" / "unit_tests" / "runners.py"
    runners.write_text(runners.read_text() + "\n# a change\n")
    assert benchmark.scorer_version() != before


def test_scores_are_one_line_per_test_with_what_the_test_is(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    lines = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert [x["page_id"] for x in lines] == ["a-p0", "a-p1"]
    assert list(lines[0]) == ["run", "provider", "page_id", "suite", "document", "test_id", "test_type",
                              "output_type", "derivation", "tags", "result", "why", "scorer"]
    assert lines[0]["run"] == run.out.name and lines[0]["provider"] == "stub"


def test_a_runs_scores_are_summarized_as_they_are_on_disk(tmp_path, monkeypatch):
    """summary.json is `summarize` over scores.jsonl's lines, so any part of the file summarizes alone."""
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data", 2)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    (s,) = benchmark.execute(p, say=QUIET).values()
    lines = [json.loads(x) for x in (p.runs[0].out / "scores.jsonl").read_text().splitlines()]
    got = scorer.summarize(lines)
    assert got == {k: v for k, v in s.items() if k in got}
    assert scorer.summarize(lines[:1])["html"]["tests"] == 1


def graded_pages(monkeypatch) -> list[str]:
    """The pages `grade_page` is called on, in order, from here on."""
    graded, real = [], benchmark._grade_page
    monkeypatch.setattr(benchmark, "_grade_page", lambda *a: graded.append(a[2].page_id) or real(*a))
    return graded


def test_a_lost_line_comes_back_on_the_next_grading(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub(supports={"html", "blocks"})})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2, blocks=True))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    path = run.out / "scores.jsonl"
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert [x["test_id"] for x in lines] == ["t0", "k0", "t1", "k1"]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines[:3]))
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert [json.loads(x)["test_id"] for x in path.read_text().splitlines()] == ["t0", "k0", "t1", "k1"]


def test_a_broken_scores_file_is_written_over_not_a_crash(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    path = run.out / "scores.jsonl"
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    del lines[0]["test_id"], lines[1]["result"]
    path.write_text("".join(json.dumps(x) + "\n" for x in lines))
    graded = graded_pages(monkeypatch)
    (s,) = benchmark.execute(p._replace(score_only=True), say=QUIET).values()
    assert graded == ["a-p0", "a-p1"] and s["pages"] == 2


# 12. Grading reads predictions/ alone, with what the run can't produce said once in settings.json.

def test_prepare_says_what_the_provider_cannot_produce(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub(supports=frozenset({"html"}))})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    benchmark.execute(p, say=QUIET)
    assert json.loads((p.runs[0].out / "settings.json").read_text())["unsupported"] == ["blocks"]


def test_a_changed_prediction_is_graded_and_the_record_is_not_read(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert s["html"]["score"] == 1.0
    (run,) = p.runs
    (run.predictions / "a-p0.json").write_text(json.dumps({"html": "<p>beta</p>"}))
    monkeypatch.setattr(benchmark, "recorded", lambda run, page_id: None)     # as if it had no records
    assert benchmark.grade(run, data.read_manifest(p.dataset)[1], say=QUIET)["html"]["score"] == 0.0


def test_a_folder_of_your_own_predictions_is_graded(tmp_path, capsys):
    """No records, no provider: predictions/ and what the system can't produce are all it takes. A page
    left out of a folder of your own is one your system didn't answer, so it fails."""
    ds = dataset(tmp_path / "data", n=2, blocks=True)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", ds, "--unsupported", "blocks"]) == 0
    assert json.loads((mine / "settings.json").read_text())["unsupported"] == ["blocks"]
    lines = [json.loads(x) for x in (mine / "scores.jsonl").read_text().splitlines()]
    assert [(x["test_id"], x["result"]) for x in lines] == [("t0", "pass"), ("k0", "unsupported"),
                                                         ("t1", "fail"), ("k1", "unsupported")]
    out = json.loads(capsys.readouterr().out)
    assert out["html"] == 0.5 and out["pages"] == 2 and out["pending"] == 0


def test_a_page_a_run_never_attempted_is_pending(tmp_path, monkeypatch):
    """In a run folder, which keeps records, a page with neither a prediction nor a record was never
    attempted (`--limit`, a stopped run): it is pending, left out and counted, not failed."""
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data", 2)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds, limit=1)
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert (s["pages"], s["pending"]) == (1, 1) and s["html"]["score"] == 1.0


def test_an_output_left_out_fails_rather_than_being_unsupported(tmp_path):
    """Unsupported is said once for the folder, so leaving an output out on a hard page fails it."""
    ds = dataset(tmp_path / "data", blocks=True)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)
    lines = [json.loads(x) for x in (mine / "scores.jsonl").read_text().splitlines()]
    assert [(x["test_id"], x["result"]) for x in lines] == [("t0", "pass"), ("k0", "fail")]


def test_a_folder_that_doesnt_say_what_it_cannot_produce_is_refused(tmp_path):
    ds = dataset(tmp_path / "data")
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    with pytest.raises(ValueError, match="--unsupported"):
        benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)


def test_the_plan_counts_what_grading_will_grade_over_the_whole_manifest(tmp_path, monkeypatch):
    """--limit chooses what to predict; grading still covers every page, and counts what it will grade."""
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data", n=3)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds, limit=1)
    (run,) = p.runs
    assert benchmark.owed(p, run) == (1, 1)
    benchmark.execute(p, say=QUIET)
    assert benchmark.owed(p._replace(pages=data.read_manifest(ds)[1]), run) == (2, 3)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    assert benchmark.owed(p._replace(runs=(benchmark.Run("mine", {}, mine),), score_only=True),
                          benchmark.Run("mine", {}, mine)) == (0, 3), "no records/: every page is graded"


def test_an_empty_selection_is_refused(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data")
    with pytest.raises(ValueError, match="no pages selected"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds, only=frozenset())


def test_a_page_whose_prediction_is_lost_is_predicted_again_not_left_pending(tmp_path, monkeypatch):
    """Grading reads predictions alone, so a record without one would never be graded."""
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    (run.predictions / "a-p0.json").unlink()
    assert benchmark.owed(p, run) == (1, 1)
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert len(calls) == 2 and s["pages"] == 1 and s["pending"] == 0


def test_an_adapter_of_your_own_is_filed_and_checked(monkeypatch):
    """`add_adapter` files a module that has the contract's names; a taken name, or a module missing
    one, is refused, naming what to do."""
    monkeypatch.setattr(registry, "ADAPTERS", dict(registry.ADAPTERS))
    monkeypatch.setattr(registry, "PROVIDERS", list(registry.PROVIDERS))
    mine = stub("mine")
    harness.add_adapter("mine", mine)
    assert registry.adapter("mine") is mine and "mine" in registry.PROVIDERS
    with pytest.raises(ValueError, match="taken"):
        harness.add_adapter("mine", mine)
    with pytest.raises(TypeError, match="missing"):
        harness.add_adapter("half", types.ModuleType("half"))


def test_a_runs_lines_are_read_back_as_written(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    assert [x["page_id"] for x in benchmark.read_scores(run)] == ["a-p0", "a-p1"]
    assert benchmark.read_scores(benchmark.Run("x", {}, tmp_path / "nothing")) == []


def test_a_folder_of_your_own_graded_for_one_suite_counts_only_it(tmp_path, capsys):
    """Grading part of the dataset on purpose: `--suites` keeps the rest from failing."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = dataset(tmp_path / "data", n=2)
    m = pathlib.Path(ds) / "manifest.parquet"
    rows = pq.read_table(m).to_pylist()
    rows[1]["suite"] = "b"
    pq.write_table(pa.Table.from_pylist(rows), m)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    assert cli.main(["grade", str(mine), "--dataset", ds]) == 0
    whole = json.loads(capsys.readouterr().out)
    assert whole["html"] == 0.5 and whole["pages"] == 2, "a page left out of your folder fails"
    assert cli.main(["grade", str(mine), "--dataset", ds, "--suites", "a"]) == 0
    one = json.loads(capsys.readouterr().out)
    assert one["html"] == 1.0 and (one["pages"], one["pending"]) == (1, 0)


def test_a_dataset_may_hold_several_manifests_over_the_same_pages(tmp_path, monkeypatch):
    """A manifest names its pages and where their gold is, so one dataset's pages can carry golds of
    several kinds, one manifest each, without copying a page."""
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data", 2))
    rows = pq.read_table(ds / "manifest.parquet").to_pylist()
    (ds / "other").mkdir()
    for r in rows:
        (ds / "other" / f"{r['page_id']}.json").write_text((ds / r["gt_path"]).read_text())
    (ds / "manifests").mkdir()
    pq.write_table(pa.Table.from_pylist([r | {"gt_path": f"other/{r['page_id']}.json"} for r in rows[:1]]),
                   ds / "manifests" / "one.parquet")
    _, pages = data.read_manifest(ds, "manifests/one.parquet")
    assert [p.gt_path for p in pages] == [str(ds.resolve() / "other" / "a-p0.json")]
    assert pages[0].doc_path == data.read_manifest(ds)[1][0].doc_path, "the same page file"
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=str(ds), manifest="manifests/one.parquet")
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert s["pages"] == 1 and s["html"]["score"] == 1.0
    assert json.loads((p.runs[0].out / "settings.json").read_text())["manifest"] == "manifests/one.parquet"
    with pytest.raises(data.ManifestError, match="no manifest nope.parquet"):
        data.read_manifest(ds, "nope.parquet")


@pytest.mark.parametrize("column, value", [("gt_path", "/abs/a-p0.json"), ("gt_path", "../a-p0.json"),
                                           ("gt_path", "gold/a-p1.json"), ("doc_path", "pages/a-p0.txt")])
def test_a_path_must_stay_inside_the_dataset_and_a_gold_name_its_page(tmp_path, column, value):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    rows = pq.read_table(ds / "manifest.parquet").to_pylist()
    pq.write_table(pa.Table.from_pylist([rows[0] | {column: value}]), ds / "manifest.parquet")
    with pytest.raises(data.ManifestError, match=f"{column} must be a path inside the dataset"):
        data.read_manifest(ds)


def test_pages_may_share_an_input_file(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data", n=2))
    rows = pq.read_table(ds / "manifest.parquet").to_pylist()
    pq.write_table(pa.Table.from_pylist([r | {"doc_path": "pages/shared.pdf"} for r in rows]),
                   ds / "manifest.parquet")
    _, pages = data.read_manifest(ds)
    assert len(pages) == 2 and pages[0].doc_path == pages[1].doc_path


def test_page_ids_must_differ_by_more_than_case(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    (row,) = pq.read_table(ds / "manifest.parquet").to_pylist()
    (ds / "gold" / "A-P0.json").write_text((ds / "gold" / "a-p0.json").read_text())
    pq.write_table(pa.Table.from_pylist([row, row | {"page_id": "A-P0", "gt_path": "gold/A-P0.json"}]),
                   ds / "manifest.parquet")
    with pytest.raises(data.ManifestError, match="ignoring case"):
        data.read_manifest(ds)


@pytest.mark.parametrize("stop, graded", [(errors.AccountFailure("out of credits"), True),
                                          (KeyboardInterrupt(), False)])
def test_a_failure_part_way_is_graded_and_an_interrupt_is_not(tmp_path, monkeypatch, stop, graded):
    def call(config):
        raise stop
    use(monkeypatch, {"stub": stub(call=call)})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    with pytest.raises(type(stop)):
        benchmark.execute(p, say=QUIET)
    assert (p.runs[0].out / "summary.json").exists() == graded


def test_check_says_whether_a_dataset_can_run(tmp_path, capsys):
    ds = pathlib.Path(dataset(tmp_path / "data", n=2))
    assert cli.main(["check", "--dataset", str(ds)]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "manifest": "manifest.parquet", "pages": 2,
                                                   "suites": 1, "inputs": 2}
    (ds / "pages" / "a-p1.pdf").unlink()
    assert cli.main(["check", "--dataset", str(ds)]) == 1
    assert "1 files the manifest names don't exist" in capsys.readouterr().err
    data.read_manifest.cache_clear()
    (ds / "pages" / "a-p1.pdf").write_bytes(b"%PDF")
    (ds / "gold" / "a-p1.json").write_text("{}")
    assert cli.main(["check", "--dataset", str(ds)]) == 1
    assert "a-p1" in capsys.readouterr().err


def test_a_run_planned_at_another_commit_of_its_dataset_warns_and_carries_on(tmp_path):
    r = benchmark.Run("stub", {}, tmp_path / "run")
    assert benchmark._another_commit(r, "abc", "abc") is None
    assert benchmark._another_commit(r, None, "abc") is None
    msg = benchmark._another_commit(r, "abc", "def")
    assert "commit abc" in msg and "commit def" in msg and "--out" in msg
