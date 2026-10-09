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

from omni_parse_bench import benchmark, cli, harness  # noqa: E402
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


def dataset(root: pathlib.Path, n: int = 1, blocks: bool = False) -> str:
    """A dataset of `n` pages, each with an html test passing on "alpha" (and a blocks test)."""
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
        rows.append({"page_id": pid, "document": "a", "suite": "a", "doc_path": f"pages/{pid}.pdf",
                     "gt_path": f"gold/{pid}.json"})
    pq.write_table(pa.Table.from_pylist(rows), root / "manifest.parquet")
    return str(root)


def record(run: benchmark.Run, pid: str = "a-p0") -> dict:
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
    assert benchmark.workers_for("datalab") == benchmark.WORKERS["datalab"]
    assert benchmark.workers_for("datalab", 3) == 3 and benchmark.workers_for("unknown") == 5


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
    (None, "VendorTimeout: timed out", True),       # a record from before failures were kept
    (None, "VendorError: HTTP 503", False),          # read conservatively: only the class
    (None, "the adapter couldn't read the answer: KeyError", False),
])
def test_retry_failed_asks_again_only_what_may_go_otherwise(failure, error, again):
    rec = {"outputs": {"html": None}, "errors": {"html": error},
           "calls": [{"outputs": ["html"]} | ({"failure": failure} if failure else {})]}
    want = frozenset({"html"})
    assert benchmark.missing(rec, want) == frozenset()
    assert benchmark.missing(rec, want, retry_failed=True) == (want if again else frozenset())


# 4. A run's dataset, gold and timeout.

def test_a_page_is_fetched_at_the_commit_its_gold_was_read_at(tmp_path, monkeypatch):
    import huggingface_hub

    got = {}

    def download(repo, path, **kwargs):
        got.update(kwargs, repo=repo)
        return str(tmp_path / "x.pdf")

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", download)
    root = tmp_path / "abc123"
    benchmark.page_file("hf://datasets/org/data@main", root, "pages/a.pdf")
    assert got["repo"] == "org/data" and got["revision"] == "abc123"


def test_a_run_folder_holds_one_dataset_and_records_its_gold(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    one, two = dataset(tmp_path / "one"), dataset(tmp_path / "two")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=one, timeout=30)
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    settings = json.loads((run.out / "settings.json").read_text())
    assert settings["dataset"] == benchmark.dataset_id(one) and settings["timeout_s"] == 30
    assert settings["gold"] == benchmark.gold_revision(one, pathlib.Path(one))
    with pytest.raises(ValueError, match="never mixes datasets"):
        benchmark.plan(["stub"], out=tmp_path / "runs", dataset=two)
    gold = pathlib.Path(one) / "gold" / "a-p0.json"
    gold.write_text(gold.read_text().replace('"alpha"', '"beta"'))
    benchmark.load.cache_clear()
    benchmark.execute(p, say=QUIET)
    settings = json.loads((run.out / "settings.json").read_text())
    assert len(settings["golds"]) == 2 and settings["golds"][-1] == settings["gold"]


def test_each_call_keeps_the_timeout_it_ran_under(tmp_path, monkeypatch):
    answers = iter([errors.VendorTimeout("slow"), contract.Call({"html": "<p>alpha</p>"})])
    use(monkeypatch, {"stub": stub(call=lambda config: next(answers))})
    data = dataset(tmp_path / "data")
    benchmark.execute(benchmark.plan(["stub"], out=tmp_path / "runs", dataset=data, timeout=5), say=QUIET)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=data, timeout=7, retry_failed=True)
    benchmark.execute(p, say=QUIET)
    rec = record(p.runs[0])
    assert [c["timeout_s"] for c in rec["calls"]] == [5, 7] and rec["timeout_s"] == 7


def test_a_changed_page_file_is_predicted_again(tmp_path, monkeypatch):
    calls = []
    use(monkeypatch, {"stub": stub(call=lambda config: calls.append(1) or contract.Call({"html": "alpha"}))})
    data = dataset(tmp_path / "data")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=data)
    benchmark.execute(p, say=QUIET)
    pdf = pathlib.Path(data) / "pages" / "a-p0.pdf"
    assert record(p.runs[0])["page_sha256"] == benchmark.file_digest(pdf)
    benchmark.execute(p, say=QUIET)
    assert len(calls) == 1
    pdf.write_bytes(b"%PDF another page")
    benchmark.execute(p, say=QUIET)
    assert len(calls) == 2, "a record of another page file is not this page's"
    old = record(p.runs[0])
    del old["page_sha256"]
    benchmark.write_json(p.runs[0].records / "a-p0.json", old)
    pdf.write_bytes(b"%PDF yet another")
    benchmark.execute(p, say=QUIET)
    assert len(calls) == 2, "a record from before page digests is trusted"


# 5. The plan counts what will be predicted.

def test_the_plan_counts_what_will_be_predicted(tmp_path, monkeypatch):
    answers = iter([errors.VendorTimeout("slow")])
    use(monkeypatch, {"stub": stub(call=lambda config: next(answers))})
    data = dataset(tmp_path / "data", blocks=True)
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=data)
    (run,) = p.runs
    revision = benchmark.gold_revision(data, pathlib.Path(data))
    assert benchmark.owed(p, run, revision, lambda g: None) == (1, 1)
    benchmark.execute(p, say=QUIET)
    assert record(run)["errors"]["blocks"] == "unsupported"
    assert benchmark.owed(p, run, revision, lambda g: None) == (0, 0), "an unsupported output is settled"
    assert benchmark.owed(p._replace(retry_failed=True), run, revision, lambda g: None) == (1, 1)
    assert "predict" in benchmark.describe(p)


# 6. Score lines carry the gold and scorer that graded them.

def test_rows_are_graded_again_when_the_scorer_changes_without_a_summary(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    (s,) = benchmark.execute(p, say=QUIET).values()
    (run,) = p.runs
    rows = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert {r["scorer"] for r in rows} == {benchmark.SCORER} and s["scorer"] == benchmark.SCORER
    assert {r["gold"] for r in rows} == {s["gold"]}
    (run.out / "summary.json").unlink()
    monkeypatch.setattr(benchmark, "SCORER", "next")
    graded = []
    real = benchmark.grade_page
    monkeypatch.setattr(benchmark, "grade_page", lambda *a: graded.append(1) or real(*a))
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert len(graded) == 2
    rows = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert {r["scorer"] for r in rows} == {"next"}


def test_a_renamed_test_is_graded_again_not_a_crash(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    data = dataset(tmp_path / "data")
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=data)
    benchmark.execute(p, say=QUIET)
    gold = pathlib.Path(data) / "gold" / "a-p0.json"
    gold.write_text(gold.read_text().replace('"t0"', '"t0-renamed"'))
    benchmark.load.cache_clear()
    (s,) = benchmark.execute(p._replace(score_only=True), say=QUIET).values()
    assert s["html"]["score"] == 1.0
    lines = [json.loads(x) for x in (p.runs[0].out / "scores.jsonl").read_text().splitlines()]
    assert [x["test_id"] for x in lines] == ["t0-renamed"]


# 7, 8. The CLI: errors in our code exit 2; scores come with their coverage.

def test_opb_benchmark_exits_2_when_our_code_errored(monkeypatch, capsys):
    clean = {"html": {"score": 0.9}, "pages": 3, "pages_pending": 1}
    for summaries, code in (({"r": clean}, 0), ({"r": clean | {"html": {"score": 0.9, "errors": 2}}}, 2)):
        monkeypatch.setattr(benchmark, "plan", lambda *a, **k: None)
        monkeypatch.setattr(benchmark, "execute", lambda p, say, s=summaries: s)
        assert cli.main(["benchmark", "--providers", "x", "-y"]) == code
        out, err = capsys.readouterr()
        assert json.loads(out) == {"r": {"html": 0.9, "pages": 3, "pages_pending": 1}}
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
        assert rec["calls"][0]["failure"]["status"] == 200 and not benchmark.retryable(rec, "html")


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
    assert benchmark.retryable(rec, "html") == retried and reason in rec["errors"]["html"]


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
    with pytest.raises(SystemExit, match="negative"):
        cli.main(["benchmark", "--providers", "datalab", "--limit", "-1", "-y"])


def test_a_missing_repo_fails_at_once_and_a_network_fault_is_retried(monkeypatch):
    import huggingface_hub
    from huggingface_hub import errors as hf_errors

    sleeps = []
    monkeypatch.setattr(benchmark.time, "sleep", sleeps.append)

    def missing(*a, **k):
        raise hf_errors.RepositoryNotFoundError.__new__(hf_errors.RepositoryNotFoundError)

    monkeypatch.setattr(huggingface_hub, "snapshot_download", missing)
    with pytest.raises(ValueError, match="RepositoryNotFoundError"):
        benchmark.dataset_root("hf://datasets/org/nothing")
    assert not sleeps
    faults = iter([OSError("reset"), "/tmp/abc"])

    def flaky(*a, **k):
        if isinstance(got := next(faults), Exception): raise got
        return got

    monkeypatch.setattr(huggingface_hub, "snapshot_download", flaky)
    assert benchmark.dataset_root("hf://datasets/org/data").name == "abc" and len(sleeps) == 1


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


def test_an_interrupted_grading_keeps_what_it_graded(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 3))
    benchmark.execute(p, say=QUIET)
    monkeypatch.setattr(benchmark, "SCORER", "next")
    real, n = benchmark.grade_page, [0]

    def once(*a):
        n[0] += 1
        if n[0] == 2: raise KeyboardInterrupt
        return real(*a)

    monkeypatch.setattr(benchmark, "grade_page", once)
    with pytest.raises(KeyboardInterrupt):
        benchmark.execute(p._replace(score_only=True), say=QUIET)
    rows = [json.loads(x) for x in (p.runs[0].out / "scores.jsonl").read_text().splitlines()]
    assert [r["page_id"] for r in rows] == ["a-p0", "a-p1", "a-p2"], "a page not yet regraded keeps its row"
    assert [r["scorer"] == "next" for r in rows] == [True, False, False]


def test_the_scorer_stamp_changes_with_the_scoring_code(tmp_path, monkeypatch):
    from omni_parse_bench import metric

    pkg = tmp_path / "omni_parse_bench"
    for name in benchmark.SCORING:
        (pkg / name).parent.mkdir(parents=True, exist_ok=True)
        (pkg / name).write_bytes((pathlib.Path(metric.__file__).parent / name).read_bytes())
    monkeypatch.setattr(metric, "__file__", str(pkg / "metric.py"))
    before = benchmark.scorer_version()
    assert before == benchmark.SCORER
    (pkg / "runners.py").write_text((pkg / "runners.py").read_text() + "\n# a change\n")
    assert benchmark.scorer_version() != before


def test_scores_are_one_line_per_test_with_what_the_test_is(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub()})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    lines = [json.loads(x) for x in (run.out / "scores.jsonl").read_text().splitlines()]
    assert [x["page_id"] for x in lines] == ["a-p0", "a-p1"]
    assert list(lines[0]) == ["run", "provider", "page_id", "suite", "document", "test_id", "test_type",
                              "output_type", "derivation", "tags", "result", "why", "record", "gold",
                              "scorer"]
    assert lines[0]["run"] == run.out.name and lines[0]["provider"] == "stub"


def graded_pages(monkeypatch) -> list[str]:
    """The pages `grade_page` is called on, in order, from here on."""
    graded, real = [], benchmark.grade_page
    monkeypatch.setattr(benchmark, "grade_page", lambda *a: graded.append(a[3].page_id) or real(*a))
    return graded


def test_a_page_of_several_tests_is_graded_again_whole_and_only_when_stale(tmp_path, monkeypatch):
    use(monkeypatch, {"stub": stub(supports={"html", "blocks"})})
    p = benchmark.plan(["stub"], out=tmp_path / "runs", dataset=dataset(tmp_path / "data", 2, blocks=True))
    benchmark.execute(p, say=QUIET)
    (run,) = p.runs
    path = run.out / "scores.jsonl"
    lines = [json.loads(x) for x in path.read_text().splitlines()]
    assert [x["test_id"] for x in lines] == ["t0", "k0", "t1", "k1"]
    graded = graded_pages(monkeypatch)
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert graded == []
    lines[1]["scorer"] = "old"   # a-p0: one stale line; a-p1: one line lost
    path.write_text("".join(json.dumps(x) + "\n" for x in lines[:3]))
    benchmark.execute(p._replace(score_only=True), say=QUIET)
    assert graded == ["a-p0", "a-p1"]
    assert [json.loads(x)["test_id"] for x in path.read_text().splitlines()] == ["t0", "k0", "t1", "k1"]


def test_a_line_missing_a_column_is_graded_again_not_a_crash(tmp_path, monkeypatch):
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
