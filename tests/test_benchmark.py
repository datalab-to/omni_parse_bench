"""The benchmark loop over stub vendors (no network): concurrency per adapter, what a resume predicts
and grades again, a run's dataset, and the CLI's exit codes."""
from __future__ import annotations

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
from omni_parse_bench.errors import UsageError  # noqa: E402
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
    with pytest.raises(UsageError, match="'abc'"):
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
    ({"class": "VendorError", "status": None}, "VendorError: no readable answer", False),
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
    with pytest.raises(UsageError, match="no folder at"):
        benchmark.grade(benchmark.Run("tesseract", {}, tmp_path / "nowhere"), ())
    (tmp_path / "empty").mkdir()
    with pytest.raises(ValueError, match="has no predictions/ folder"):
        benchmark.grade(benchmark.Run("tesseract", {}, tmp_path / "empty"), ())


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
    with pytest.raises(UsageError, match="holds a run on dataset"):
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

def test_opb_benchmark_prints_each_runs_summary(monkeypatch, capsys):
    summaries = {"r": {"html": {"score": 0.9}, "pages": 3, "failed": 0, "pending": 1}}
    monkeypatch.setattr(benchmark, "plan", lambda *a, **k: benchmark.Plan((), (), "", "", 1, 0, False))
    monkeypatch.setattr(benchmark, "describe", lambda p: "")
    monkeypatch.setattr(benchmark, "execute", lambda p, say: summaries)
    assert cli.main(["benchmark", "--providers", "x", "-y"]) == 0
    assert json.loads(capsys.readouterr().out) == summaries, "each run's summary, as summary.json holds it"


def test_a_scorer_that_raises_stops_grading_and_writes_nothing(tmp_path, monkeypatch):
    """A crash in our scorer is a bug of ours: raised, naming the run, the page and the test, never a score
    with that test left out."""
    from omni_parse_bench.scorers.unit_tests import runners

    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    benchmark.predict_all(p)
    (run,) = p.runs
    monkeypatch.setitem(runners.TYPES, "present", (runners.TYPES["present"][0], lambda t, v: 1 / 0))
    with pytest.raises(ZeroDivisionError) as e:
        benchmark.grade_all(p, say=QUIET)
    notes = " ".join(e.value.__notes__)
    assert "t0" in notes and "a-p0" in notes and run.out.name in notes
    assert not (run.out / "summary.json").exists() and not (run.out / "scores.jsonl").exists()


def test_a_score_is_said_with_its_coverage(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    said = []
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 3), limit=2)
    (s,) = benchmark.execute(p, say=said.append).values()
    assert said[0].endswith("headline — (1 pending: a headline needs every page); 2 of 3 pages graded, "
                            "0 failed")
    assert s["headline"] is None and s["html"]["score"] == 1.0, "no headline while a page is pending"
    assert s["per_suite"] == {"a": {"headline": None, "score": 1.0, "pages": 2, "failed": 0, "pending": 1}}
    said.clear()
    (s,) = benchmark.execute(p._replace(pages=data.read_manifest(p.dataset)[1]), say=said.append).values()
    assert said[0].endswith("headline 1.000; 3 of 3 pages graded, 0 failed") and s["headline"] == 1.0


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

def test_a_bad_count_or_an_empty_options_list_is_refused(tmp_path):
    ds = dataset(tmp_path / "data")
    for kwargs in ({"limit": -1}, {"sample": -2}, {"workers": -1}):
        with pytest.raises(UsageError, match="negative"):
            benchmark.plan(["datalab"], dataset=ds, **kwargs)
    with pytest.raises(UsageError, match="empty list"):
        benchmark.plan(["datalab"], dataset=ds, options={"datalab": []})
    assert cli.main(["benchmark", "--providers", "datalab", "--dataset", ds, "--limit", "-1", "-y"]) == 1


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
    assert {k: v for k, v in got.items() if k != "per_suite"} == {k: s[k] for k in got if k != "per_suite"}
    assert all(s["per_suite"][k].items() >= v.items() for k, v in got["per_suite"].items())
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
    assert out["html"]["score"] == 0.5 and out["pages"] == 2 and out["pending"] == 0
    assert out == json.loads((mine / "summary.json").read_text()), "stdout is the folder's summary.json"


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
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "alpha"}))
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


def test_a_prediction_lost_beside_its_record_is_rebuilt_not_paid_for_again(tmp_path, monkeypatch, capsys):
    """The record is the source of truth for an answer: a lost or corrupt prediction is written from it."""
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", n=2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    (run.predictions / "a-p0.json").unlink()
    (run.predictions / "a-p1.json").write_text("{not json")
    assert benchmark.owed(p, run) == (0, 2), "nothing to pay for"
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert len(calls) == 2 and s["pages"] == 2 and s["failed"] == 0
    assert json.loads((run.predictions / "a-p0.json").read_text()) == {"html": "alpha"}
    (run.predictions / "a-p0.json").unlink()
    assert cli.main(["reparse", str(run.out)]) == 0 and "1 prediction rebuilt" in capsys.readouterr().err
    assert (run.predictions / "a-p0.json").exists()


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
    with pytest.raises(UsageError, match="no folder"):
        benchmark.read_scores(benchmark.Run("x", {}, tmp_path / "nothing"))
    (tmp_path / "never").mkdir()
    assert benchmark.read_scores(benchmark.Run("x", {}, tmp_path / "never")) == []


def test_a_folder_of_your_own_is_graded_over_the_whole_manifest(tmp_path, capsys):
    """A page left out of your folder fails, and each suite says how its pages went."""
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
    assert whole["html"]["score"] == 0.5 and whole["pages"] == 2, "a page left out of your folder fails"
    assert whole["per_suite"]["a"]["failed"] == 0 and whole["per_suite"]["b"]["failed"] == 1
    with pytest.raises(SystemExit):
        cli.main(["grade", str(mine), "--suites", "a"])


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
    assert [p.gt_path for p in pages] == [ds.resolve() / "other" / "a-p0.json"]
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


@pytest.mark.parametrize("suite, read", [(None, "other"), ("", "other"), ("tables", "tables")])
def test_a_page_with_no_suite_is_in_other(tmp_path, suite, read):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    (row,) = pq.read_table(ds / "manifest.parquet").to_pylist()
    pq.write_table(pa.Table.from_pylist([row | {"suite": suite}]), ds / "manifest.parquet")
    assert data.read_manifest(ds)[1][0].suite == read


def test_a_page_id_must_be_a_filename(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    (row,) = pq.read_table(ds / "manifest.parquet").to_pylist()
    pq.write_table(pa.Table.from_pylist([row | {"page_id": "a/p0", "gt_path": "gold/a/p0.json"}]),
                   ds / "manifest.parquet")
    with pytest.raises(data.ManifestError, match="page_id must be a filename"):
        data.read_manifest(ds)


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
    assert "don't exist: 1 file" in capsys.readouterr().err
    data.read_manifest.cache_clear()
    (ds / "pages" / "a-p1.pdf").write_bytes(b"%PDF")
    (ds / "gold" / "a-p1.json").write_text("{}")
    assert cli.main(["check", "--dataset", str(ds)]) == 1
    assert "a-p1" in capsys.readouterr().err


# 14. Guardrails: what a user gets wrong is refused, or said, never graded silently.

def test_grade_reads_a_runs_own_dataset_and_refuses_another(tmp_path, monkeypatch, capsys):
    import shutil

    use(monkeypatch, {"stub": stub()})
    ds = dataset(tmp_path / "data", n=2)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=ds)
    benchmark.execute(p, say=QUIET)
    run = p.runs[0].out
    assert cli.main(["grade", str(run)]) == 0, "no --dataset: the run's own"
    assert json.loads(capsys.readouterr().out)["html"]["score"] == 1.0
    other = tmp_path / "other"
    shutil.copytree(ds, other)
    before = (run / "summary.json").read_text()
    assert cli.main(["grade", str(run), "--dataset", str(other)]) == 1
    assert "holds a run on dataset" in capsys.readouterr().err
    assert (run / "summary.json").read_text() == before, "a refused grading writes nothing"
    assert cli.main(["grade", str(run), "--manifest", "other.parquet"]) == 1
    assert "holds a run on manifest" in capsys.readouterr().err
    assert cli.main(["grade", str(run), "--unsupported", "blocks"]) == 1
    assert "--unsupported is for a folder of your own" in capsys.readouterr().err
    assert json.loads((run / "settings.json").read_text())["unsupported"] == ["blocks"], "left as it was"
    assert cli.main(["grade", str(tmp_path / "typo"), "--unsupported", "blocks"]) == 1
    assert "no folder at" in capsys.readouterr().err
    assert not (tmp_path / "typo").exists()


def test_grade_says_which_predictions_it_could_not_use(tmp_path, caplog):
    ds = dataset(tmp_path / "data", n=3)
    mine = tmp_path / "mine"
    (mine / "predictions" / "nested").mkdir(parents=True)
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>", "markdown": "x"}))
    (mine / "predictions" / "a-p1.json").write_text("not json")
    (mine / "predictions" / "a-p2.pdf.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    with caplog.at_level(logging.WARNING):
        s = benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)
    assert s["html"]["score"] == pytest.approx(1 / 3), "an extra key is ignored; the page still passes"
    assert "2 files in predictions/ named for no page" in caplog.text
    assert "1 prediction couldn't be read" in caplog.text and "a-p1" in caplog.text
    assert not list(mine.glob("*.tmp")), "both files moved into place"


def test_a_mistake_on_the_command_line_is_a_message_not_a_traceback(tmp_path, capsys, monkeypatch):
    ds = dataset(tmp_path / "data")
    assert cli.main(["benchmark", "--providers", "stub", "--dataset", ds, "--suites", "zz", "-y"]) == 1
    assert capsys.readouterr().err.startswith("opb benchmark: ")
    assert cli.main(["check", "--dataset", "hf:/datasets/x/y"]) == 1
    assert "slash missing" in capsys.readouterr().err
    (tmp_path / "local.parquet").write_bytes(b"")
    assert cli.main(["check", "--dataset", ds, "--manifest", str(tmp_path / "local.parquet")]) == 1
    assert "must be a path inside the dataset, relative to it" in capsys.readouterr().err
    monkeypatch.chdir(tmp_path)
    assert cli.main(["check", "--dataset", ds, "--manifest", "local.parquet"]) == 1
    assert "a manifest is a path inside the dataset" in capsys.readouterr().err


def test_check_refuses_a_manifest_with_no_pages(tmp_path, capsys):
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    table = pq.read_table(ds / "manifest.parquet")
    pq.write_table(table.slice(0, 0), ds / "manifest.parquet")
    assert cli.main(["check", "--dataset", str(ds)]) == 1
    assert "names no pages" in capsys.readouterr().err


def test_score_says_what_is_wrong_with_what_it_was_given(tmp_path, capsys):
    ds = pathlib.Path(dataset(tmp_path / "data"))
    gold_file = str(ds / "gold" / "a-p0.json")
    for content, why in [([], "holds a JSON list"), ({"outputs": {"html": "x"}}, "record from opb predict")]:
        (tmp_path / "pred.json").write_text(json.dumps(content))
        assert cli.main(["score", "--pred", str(tmp_path / "pred.json"), "--gold", gold_file]) == 1
        assert why in capsys.readouterr().err
    assert cli.main(["score", "--pred", str(tmp_path / "nope.json"), "--gold", gold_file]) == 1
    assert "--pred" in (err := capsys.readouterr().err) and "no such file" in err
    with pytest.raises(SystemExit):
        cli.main(["score", "--pred", str(tmp_path / "pred.json"), "--gold", gold_file,
                  "--unsupported", "htm"])


def test_a_gold_of_the_wrong_shape_is_a_gold_error_naming_its_page(tmp_path):
    for i, content in enumerate(["[]", '{"tests": [1]}', "{not json"]):
        f = tmp_path / f"p{i}.json"
        f.write_text(content)
        with pytest.raises(gold.GoldError, match=f"p{i}"):
            gold.read(f)


def test_wrong_kinds_of_values_are_refused_by_name(tmp_path, monkeypatch):
    pages = data.read_manifest(dataset(tmp_path / "data", n=2))[1]
    with pytest.raises(TypeError, match="not the string"):
        data.select(pages, "a")
    with pytest.raises(ValueError, match="limit is -1"):
        data.select(pages, limit=-1)
    assert len(data.select(pages, only=["a-p0"])) == 1, "any iterable of ids"
    assert data.select((), sample=3) == ()
    use(monkeypatch, {"stub": stub()})
    with pytest.raises(TypeError, match="not the string"):
        benchmark.plan("stub", dataset="unused")
    with pytest.raises(TypeError, match="workers is a number"):
        benchmark.plan(["stub"], dataset="unused", workers="3")
    for kwargs, why in [({"timeout": -5}, "--timeout"), ({"workers": -3}, "each adapter's default")]:
        with pytest.raises(UsageError, match=why):
            benchmark.plan(["stub"], dataset="unused", **kwargs)
    with pytest.raises(ValueError, match="option tier is a str"):
        benchmark.plan(["stub"], dataset="unused", options={"stub": {"tier": 3}})
    import pyarrow.parquet as pq

    empty = pathlib.Path(dataset(tmp_path / "empty"))
    pq.write_table(pq.read_table(empty / "manifest.parquet").slice(0, 0), empty / "manifest.parquet")
    with pytest.raises(data.ManifestError, match="names no pages"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=str(empty))


def test_output_names_are_checked_where_they_are_given(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    (tmp_path / "p.pdf").write_bytes(b"%PDF")
    with pytest.raises(TypeError, match="not the string"):
        harness.predict("stub", tmp_path / "p.pdf", "html")
    with pytest.raises(ValueError, match="unknown output types"):
        harness.predict("stub", tmp_path / "p.pdf", {"markdown"})


def test_an_adapter_of_yours_is_keyed_by_the_name_it_was_filed_under(monkeypatch):
    m = stub("acme.parser")
    monkeypatch.setattr(registry, "ADAPTERS", dict(registry.ADAPTERS))
    monkeypatch.setattr(registry, "PROVIDERS", list(registry.PROVIDERS))
    registry.add_adapter("acme", m)
    assert registry.resolve("acme") == "acme" and registry.resolve("datalab") == "datalab"
    assert registry.resolve("openai/gpt-5.6-sol") == "llm"
    assert benchmark._per_adapter({"acme": 2}) == {"acme": 2}
    with pytest.raises(ValueError, match="isn't one"):
        benchmark._per_adapter({"acme.parser": 2})


def test_a_bug_in_an_adapter_stops_its_runs_naming_the_page(tmp_path, monkeypatch):
    def broken(config):
        raise RuntimeError("a bug in the adapter")
    use(monkeypatch, {"stub": stub(call=broken)})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"))
    with pytest.raises(RuntimeError) as e:
        benchmark.execute(p, say=QUIET)
    assert any("raised while predicting a-p0 with the stub adapter" in n for n in e.value.__notes__)


def test_options_and_reparse_say_what_is_wrong(tmp_path, capsys):
    with pytest.raises(ValueError, match="neither inline JSON nor a file"):
        cli.read_options("opts.jsn")
    with pytest.raises(ValueError, match="must be a JSON object"):
        cli.read_options("[1]")
    assert cli.main(["reparse", str(tmp_path)]) == 1
    assert "no records/" in capsys.readouterr().err
    (tmp_path / "records").mkdir()
    (tmp_path / "records" / "a.json").write_text("{}")
    assert cli.main(["reparse", str(tmp_path)]) == 1
    assert "a.json isn't a record" in capsys.readouterr().err


def test_a_run_planned_at_another_commit_of_its_dataset_warns_and_carries_on(tmp_path):
    r = benchmark.Run("stub", {}, tmp_path / "run")
    assert benchmark._another_commit(r, "abc", "abc") is None
    assert benchmark._another_commit(r, None, "abc") is None
    msg = benchmark._another_commit(r, "abc", "def")
    assert "commit abc" in msg and "commit def" in msg and "--out" in msg


# 14. What the dogfood runs found.

def test_a_folder_of_yours_keeps_the_dataset_and_manifest_its_first_grading_used(tmp_path, capsys):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data", n=2))
    rows = pq.read_table(ds / "manifest.parquet").to_pylist()
    (ds / "manifests").mkdir()
    pq.write_table(pa.Table.from_pylist(rows[:1]), ds / "manifests" / "one.parquet")
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    for r in rows:
        (mine / "predictions" / f"{r['page_id']}.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", "nope", "--unsupported"]) == 1
    capsys.readouterr()
    assert not (mine / "settings.json").exists(), "a failed grading writes nothing"
    assert cli.main(["grade", str(mine), "--dataset", str(ds), "--manifest", "manifests/one.parquet",
                     "--unsupported"]) == 0
    said = json.loads((mine / "settings.json").read_text())
    assert said == {"dataset": data.dataset_id(ds), "manifest": "manifests/one.parquet", "unsupported": []}
    capsys.readouterr()
    assert cli.main(["grade", str(mine)]) == 0, "no flags: the folder's own dataset and manifest"
    assert json.loads(capsys.readouterr().out)["pages"] == 1
    assert cli.main(["grade", str(mine), "--manifest", "manifest.parquet"]) == 1
    assert "holds a run on manifest" in capsys.readouterr().err


def test_a_prediction_is_read_only_under_its_exact_name(tmp_path, caplog):
    ds = dataset(tmp_path / "data", n=2)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    (mine / "predictions" / "A-P1.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    with caplog.at_level(logging.WARNING):
        s = benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)
    assert s["html"]["score"] == 0.5 and s["failed"] == 1, "A-P1.json is a-p1's on no disk"
    assert "A-P1.json" in caplog.text and "named exactly (case too)" in caplog.text


def test_a_run_never_mixes_manifests(tmp_path, monkeypatch):
    import pyarrow as pa
    import pyarrow.parquet as pq

    use(monkeypatch, {"stub": stub()})
    ds = pathlib.Path(dataset(tmp_path / "data", n=2))
    pq.write_table(pa.Table.from_pylist(pq.read_table(ds / "manifest.parquet").to_pylist()[:1]),
                   ds / "half.parquet")
    benchmark.execute(benchmark.plan(["stub"], out=tmp_path / "runs", dataset=str(ds)), say=QUIET)
    with pytest.raises(UsageError, match="holds a run on manifest"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=str(ds), manifest="half.parquet")
    with pytest.raises(UsageError, match="never predicted under this --out"):
        benchmark.plan(["stub"], out=tmp_path / "elsewhere", dataset=str(ds), score_only=True)


def test_an_option_written_two_ways_is_one_run(tmp_path, monkeypatch):
    m = stub()

    @dataclasses.dataclass(frozen=True)
    class Config:
        delay: float = 0.0

    m.Config = Config
    use(monkeypatch, {"stub": m})
    with pytest.raises(ValueError, match="more than once"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data"),
                       options={"stub": [{}, {"delay": 0}]})
    with pytest.raises(ValueError, match="option delay is a float"):
        registry.config_for("stub", {"delay": "0"})
    with pytest.raises(ValueError) as e:
        registry.config_for("stub", {"dely": 1})
    assert "'dely'" in str(e.value) and "'delay'" in str(e.value) and "__init__" not in str(e.value)


def test_failures_are_counted_and_said(tmp_path, monkeypatch):
    answers = iter([contract.Call({"html": "<p>alpha</p>"}, cost=contract.Cost(usd=0.01)),
                    errors.VendorError("bad request", status=400)])
    use(monkeypatch, {"stub": stub(call=lambda config: next(answers))})
    said = []
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", n=2), workers=1)
    (s,) = benchmark.execute(p, say=said.append).values()
    assert s["failed"] == 1 and s["per_suite"]["a"]["failed"] == 1 and s["credits"] is None
    assert said[0].endswith("2 of 2 pages graded, 1 failed")


def test_an_account_failure_or_an_interrupt_is_one_line(tmp_path, monkeypatch, capsys):
    ds = dataset(tmp_path / "data")
    for stop, code, said in [(errors.AccountFailure("out of credits"), 1, "rerun to resume"),
                             (KeyboardInterrupt(), 130, "interrupted; rerun to resume")]:
        use(monkeypatch, {"stub": stub(call=lambda config, stop=stop: stop)})
        assert cli.main(["benchmark", "--providers", "stub", "--dataset", ds, "--out", str(tmp_path / "r"),
                         "-y"]) == code
        err = capsys.readouterr().err
        assert said in err and "Traceback" not in err


def test_check_names_the_row_of_a_missing_file(tmp_path, capsys):
    ds = pathlib.Path(dataset(tmp_path / "data"))
    (ds / "pages" / "a-p0.pdf").unlink()
    assert cli.main(["check", "--dataset", str(ds)]) == 1
    assert "a-p0 doc_path" in capsys.readouterr().err


def test_a_pages_file_skips_blank_lines_and_comments(tmp_path):
    (tmp_path / "ids").write_text("a-p0  # the first\n\n# a note\na-p1\n")
    assert cli.read_ids(tmp_path / "ids", "--pages") == {"a-p0", "a-p1"}
    with pytest.raises(UsageError, match="--pages"):
        cli.read_ids(tmp_path / "nope", "--pages")


def test_score_refuses_an_unknown_output_name():
    with pytest.raises(ValueError, match="aren't"):
        scorer.score({}, (), unsupported={"block"})
    with pytest.raises(ValueError, match="collection of output types"):
        scorer.score({}, (), unsupported="blocks")


# The two kinds of user-facing error, and the folder's settings.

def test_a_users_mistake_is_a_usage_error_and_a_stopped_run_a_stop():
    from omni_parse_bench.errors import Stop

    assert issubclass(data.ManifestError, UsageError) and issubclass(gold.GoldError, UsageError)
    assert issubclass(UsageError, ValueError), "a library caller may still catch ValueError"
    for e in (errors.AccountFailure, errors.MissingCredential, errors.MissingDependency):
        assert issubclass(e, Stop) and not issubclass(e, UsageError)
    assert issubclass(errors.MissingDependency, ImportError)


def test_suites_may_be_any_iterable_read_once(tmp_path):
    pages = data.read_manifest(dataset(tmp_path / "data", n=2))[1]
    assert len(data.select(pages, (s for s in ["a"]))) == 2, "a generator is read once"
    assert len(data.select(pages, [])) == 2, "no suites is every suite"


def test_an_unreadable_settings_json_is_named(tmp_path):
    (tmp_path / "settings.json").write_text("{nope")
    with pytest.raises(UsageError, match="settings.json isn't readable JSON"):
        benchmark.settled(tmp_path)
    (tmp_path / "settings.json").write_text("[]")
    with pytest.raises(UsageError, match="holds a JSON list"):
        benchmark.settled(tmp_path)
    assert benchmark.settled(tmp_path / "nothing") == {}


def test_grade_prints_the_summary_and_a_closing_line(tmp_path, capsys):
    ds = dataset(tmp_path / "data")
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", ds, "--unsupported"]) == 0
    loud = capsys.readouterr()
    assert "headline 1.000" in loud.err and json.loads(loud.out)["headline"] == 1.0
    with pytest.raises(SystemExit):
        cli.main(["grade", str(mine), "-q"])


def test_an_interrupt_says_resume_only_for_benchmark(monkeypatch, capsys):
    def interrupted(a): raise KeyboardInterrupt
    monkeypatch.setattr(cli, "cmd_check", interrupted)
    assert cli.main(["check"]) == 130
    assert capsys.readouterr().err == "opb check: interrupted\n"


def test_the_package_exports_the_scorer_and_the_dataset():
    import omni_parse_bench as opb

    assert {"data", "scorers", "gold", "score", "lines", "summarize", "check", "Verdict"} <= set(opb.__all__)
    assert not hasattr(opb, "__version__"), "the version is the distribution's: importlib.metadata"


# 15. Round two: what a user's slip costs is refused, said or rebuilt; never paid for twice.

def own(tmp_path, ds, answers: dict[str, object], name: str = "mine") -> pathlib.Path:
    """A folder of your own predictions, `answers` by file name."""
    out = tmp_path / name
    (out / "predictions").mkdir(parents=True)
    for f, x in answers.items():
        (out / "predictions" / f).write_text(x if isinstance(x, str) else json.dumps(x))
    return out


def test_a_grading_that_matches_no_page_is_refused_and_writes_nothing(tmp_path, capsys):
    ds = dataset(tmp_path / "data")
    for answers in ({"invoice-p1.json": {"html": "x"}}, {}):
        mine = own(tmp_path, ds, answers, name=f"mine{len(answers)}")
        assert cli.main(["grade", str(mine), "--dataset", ds, "--unsupported"]) == 1
        assert "--dataset" in capsys.readouterr().err
        assert sorted(f.name for f in mine.iterdir()) == ["predictions"], "nothing written, nothing locked"


def test_a_folder_holds_one_unsupported(tmp_path, capsys):
    ds = dataset(tmp_path / "data", blocks=True)
    mine = own(tmp_path, ds, {"a-p0.json": {"html": "<p>alpha</p>"}})
    assert cli.main(["grade", str(mine), "--dataset", ds, "--unsupported", "blocks"]) == 0
    assert cli.main(["grade", str(mine), "--unsupported", "blocks"]) == 0, "the same, again, is fine"
    capsys.readouterr()
    assert cli.main(["grade", str(mine), "--unsupported"]) == 1
    assert "--unsupported blocks" in capsys.readouterr().err
    assert json.loads((mine / "settings.json").read_text())["unsupported"] == ["blocks"]


def test_a_folder_of_your_own_with_records_is_yours(tmp_path, capsys):
    """A run is a folder whose settings.json names a provider; records/ alone doesn't make one."""
    ds = dataset(tmp_path / "data", n=2)
    mine = own(tmp_path, ds, {"a-p0.json": {"html": "<p>alpha</p>"}})
    (mine / "records").mkdir()
    assert cli.main(["grade", str(mine), "--dataset", ds, "--unsupported"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert (s["pages"], s["failed"], s["pending"]) == (2, 1, 0), "a page left out of your folder fails"


def test_predictions_under_no_output_type_are_said(tmp_path, caplog):
    ds = dataset(tmp_path / "data")
    mine = own(tmp_path, ds, {"a-p0.json": {"markdown": "alpha"}})
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    with caplog.at_level(logging.WARNING):
        s = benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)
    assert s["failed"] == 1 and "markdown" in caplog.text and "a-p0" in caplog.text


def test_grading_part_of_a_folders_manifest_says_so(tmp_path, caplog, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", n=3))
    benchmark.predict_all(p)
    with caplog.at_level(logging.WARNING):
        benchmark.grade(p.runs[0], p.pages[:1], say=QUIET)
    assert "1 page of its manifest's 3" in caplog.text


def test_a_stop_stops_the_workers_at_once_and_its_summaries_are_printed(tmp_path, monkeypatch, capsys):
    calls = []

    def call(config):
        calls.append(1)
        return errors.AccountFailure("out of credits") if len(calls) == 2 else contract.Call({"html": "a"})
    use(monkeypatch, {"stub": stub(call=call)})
    code = cli.main(["benchmark", "--providers", "stub", "--dataset", dataset(tmp_path / "data", n=4),
                     "--out", str(tmp_path / "runs"), "--workers", "1", "-y"])
    out, err = capsys.readouterr()
    assert code == 1 and len(calls) == 2, "nothing queued is sent after the stop"
    (s,) = json.loads(out).values()
    assert (s["pages"], s["pending"], s["headline"]) == (1, 3, None) and "AccountFailure" in err


def test_a_dataset_offline_and_uncached_is_refused_at_once(monkeypatch):
    from huggingface_hub import errors as hf_errors
    import huggingface_hub

    tries = []
    def offline(*a, **k):
        tries.append(1)
        raise hf_errors.LocalEntryNotFoundError("x")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", offline)
    with pytest.raises(ValueError, match="cache"):
        data.download_dataset("hf://datasets/someone/nowhere@nope")
    assert len(tries) == 1


def test_a_manifest_spelled_another_way_is_the_same_manifest(tmp_path):
    ds = dataset(tmp_path / "data")
    mine = own(tmp_path, ds, {"a-p0.json": {"html": "<p>alpha</p>"}})
    assert cli.main(["grade", str(mine), "--dataset", ds, "--manifest", "./manifest.parquet",
                     "--unsupported"]) == 0
    assert json.loads((mine / "settings.json").read_text())["manifest"] == "manifest.parquet"
    assert cli.main(["grade", str(mine), "--manifest", "manifest.parquet"]) == 0


def test_messages_for_files_that_are_folders_and_loose_predictions(tmp_path, capsys):
    gold_file = tmp_path / "g.json"
    gold_file.write_text(json.dumps({"tests": []}))
    assert cli.main(["score", "--pred", str(tmp_path), "--gold", str(gold_file)]) == 1
    assert "is a folder" in capsys.readouterr().err
    flat = tmp_path / "flat"
    flat.mkdir()
    (flat / "a-p0.json").write_text("{}")
    assert cli.main(["grade", str(flat)]) == 1
    assert "flat/predictions" in capsys.readouterr().err


def test_ids_differing_only_in_case_show_both_spellings(tmp_path):
    import pyarrow as pa
    import pyarrow.parquet as pq

    ds = pathlib.Path(dataset(tmp_path / "data"))
    (row,) = pq.read_table(ds / "manifest.parquet").to_pylist()
    (ds / "gold" / "A-P0.json").write_text((ds / "gold" / "a-p0.json").read_text())
    pq.write_table(pa.Table.from_pylist([row, row | {"page_id": "A-P0", "gt_path": "gold/A-P0.json"}]),
                   ds / "manifest.parquet")
    with pytest.raises(data.ManifestError) as e:
        data.read_manifest(ds)
    assert "a-p0" in str(e.value) and "A-P0" in str(e.value)


def test_a_wholly_unsupported_output_keeps_its_count(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", blocks=True))
    (s,) = benchmark.execute(p, say=QUIET).values()
    assert s["blocks"]["score"] is None and s["blocks"]["unsupported"] == 1


def test_a_prediction_with_a_byte_order_mark_reads_as_its_json(tmp_path):
    ds = dataset(tmp_path / "data")
    mine = own(tmp_path, ds, {})
    bom = b"\xef\xbb\xbf"
    (mine / "predictions" / "a-p0.json").write_bytes(bom + json.dumps({"html": "<p>alpha</p>"}).encode())
    (mine / "settings.json").write_text(json.dumps({"unsupported": []}))
    s = benchmark.grade(benchmark.Run("mine", {}, mine), data.read_manifest(ds)[1], say=QUIET)
    assert s["failed"] == 0 and s["html"]["score"] == 1.0
