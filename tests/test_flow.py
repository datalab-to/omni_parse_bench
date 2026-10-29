"""The whole benchmark on a small dataset made here, offline: predicting, resuming, grading, the command line,
and the rules opb adds to the core's (what a page asks for, a server that isn't running).

Each page has one html test, that the page's html holds "alpha", and one blocks test, that a block labelled
text holds it; a page made `blocks_only` has the blocks test alone. The stub system answers html only, with
"alpha" in it.
"""
from __future__ import annotations

import dataclasses
import json
import socket
import subprocess
import sys
from pathlib import Path
from typing import Any, ClassVar

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from omni_bench_core import config  # noqa: E402

from omni_parse_bench import benchmark, cli, harness  # noqa: E402
from omni_parse_bench import data as opb_data  # noqa: E402
from omni_parse_bench.harness import contract  # noqa: E402
from omni_parse_bench.harness import errors as harness_errors  # noqa: E402


def configured(system: str, data: str, *sets: str) -> list[str]:
    """`opb run` of the config `opb init` writes for `system` on dataset `data`, written beside it, each of
    `sets` (`path=value`) given as `--set`."""
    import yaml

    c = config.template(harness.system, system, dataset=data, manifest="manifest.parquet",
                        scorers={"unit_tests": {}}, timeout=900)
    path = Path(data).parent / f"{system}.yaml"
    path.write_text(yaml.safe_dump(c, sort_keys=False))
    return ["run", "--config", str(path), *[x for kv in sets for x in ("--set", kv)]]


def raised(argv: list[str], kind: type[BaseException] = ValueError) -> str:
    """What `opb argv` raised, as it is: the exception's message, then its notes."""
    with pytest.raises(kind) as got:
        cli.main(argv)
    return "\n".join([str(got.value), *getattr(got.value, "__notes__", [])])

CALLS: list[str] = []
WANTS: list[frozenset[str]] = []   # what each `requests` was given
BROKEN: set[str] = set()           # pages whose answer `parse` crashes on: a bug in `parse`
WRONG: set[str] = set()            # pages `parse` reads wrongly, without raising


@dataclasses.dataclass(frozen=True)
class Alpha(harness.Parser):
    """Answers every page with html holding "alpha"."""

    name: ClassVar[str] = "alpha"
    SUPPORTS: ClassVar[frozenset[str]] = frozenset({"html"})

    def requests(self, wants):
        WANTS.append(wants)
        return [contract.Request(frozenset(wants), {})]

    def send(self, page, request, *, timeout):
        CALLS.append(page.stem)
        return contract.Call({"html": "<p>alpha beta</p>", "page": page.stem}, cost=contract.Cost(usd=0.01))

    def parse(self, raw, request):
        if raw.get("page") in BROKEN: raise KeyError("html")
        if raw.get("page") in WRONG: return {"html": "<p>wrong</p>"}, {}
        return {"html": raw["html"]}, {}


def dataset(root, n: int = 3, blocks_only: int = 0) -> str:
    """`n` pages, each with an html test and a blocks test, then `blocks_only` pages with a blocks test
    alone."""
    (root / "gold").mkdir(parents=True)
    (root / "pages").mkdir()
    rows = []
    for i in range(n + blocks_only):
        pid = f"a-p{i}"
        (root / "pages" / f"{pid}.pdf").write_bytes(b"%PDF")
        html = [{"id": f"h{i}", "test_type": "present", "output_type": "html", "derivation": "authored",
                 "tags": [], "args": {"content": {"text": "alpha", "max_diffs": 0}}, "settings": {}}]
        tests = [*(html if i < n else []),
                 {"id": f"b{i}", "test_type": "layout_kind", "output_type": "blocks",
                  "derivation": "authored", "tags": [],
                  "args": {"content": {"text": "alpha", "max_diffs": 0, "place": [[0.1, 0.1, 0.4, 0.2]]}},
                  "settings": {"kind": "text"}}]
        (root / "gold" / f"{pid}.json").write_text(json.dumps({"tests": tests}))
        rows.append({"page_id": pid, "document": f"d{i}", "suite": "s", "doc_path": f"pages/{pid}.pdf",
                     "gt_path": f"gold/{pid}.json", "outputs": ["blocks", "html"] if i < n else ["blocks"]})
    pq.write_table(pa.Table.from_pylist(rows), root / "manifest.parquet")
    return str(root)


def test_an_html_only_system_is_predicted_graded_and_resumed(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data"))
    CALLS.clear()
    name = (g := b.run(Alpha(), tmp_path / "runs"))["run"]
    assert sorted(CALLS) == ["a-p0", "a-p1", "a-p2"]
    [s] = g["scorers"].values()
    assert s["scored"]["families"] == {"text": {"score": 1.0, "tests": 3, "documents": 3},
                             "layout": {"score": 0.0, "tests": 3, "documents": 3}}, s
    assert (s["headline"], s["coverage"], s["failed"]) == (0.5, 1.0, 0), "no blocks: layout 0, not a failure"
    assert s["scored"]["headline_is"] == "the mean of the families' scores" and "partial" not in s
    assert g["cost"]["usd"] == 0.03
    CALLS.clear()
    b.run(Alpha(), tmp_path / "runs", resume=name)
    assert CALLS == [], "a resumed run calls nothing"
    details = (tmp_path / "runs" / name / b.scorers[0].folder_name / "details" / "a-p0.jsonl").read_text()
    html, blocks = map(json.loads, details.splitlines())
    assert html["result"] == "pass" and blocks["result"] == "fail" and blocks["why"] == "no blocks output"


def test_a_page_wanting_nothing_the_system_supports_is_not_sent_and_fails_its_tests(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data", 2, blocks_only=1))
    CALLS.clear()
    WANTS.clear()
    name = (g := b.run(Alpha(), tmp_path / "runs"))["run"]
    assert sorted(CALLS) == ["a-p0", "a-p1"], "the blocks-only page isn't sent"
    assert WANTS and all(WANTS), "no adapter is asked for an empty set of outputs"
    rec = json.loads((tmp_path / "runs" / name / "records" / "a-p2.json").read_text())
    assert (rec["output"], rec["error"], rec["cost"]["usd"]) == ({"pages": [{}]}, None, None), rec
    [s] = g["scorers"].values()
    assert (s["coverage"], s["failed"], s["rows"]) == (1.0, 0, 3), "not a failed page: coverage stays 1"
    assert s["scored"]["families"]["layout"] == {"score": 0.0, "tests": 3, "documents": 3}, s


def test_details_lines_are_test_lines_that_summarize_reads(tmp_path):
    from omni_parse_bench.scorers import unit_tests

    b = benchmark.default(dataset(tmp_path / "data"))
    name = (g := b.run(Alpha(), tmp_path / "runs"))["run"]
    folder = tmp_path / "runs" / name / b.scorers[0].folder_name / "details"
    lines = [json.loads(x) for f in sorted(folder.iterdir()) for x in f.read_text().splitlines()]
    assert {(x["page_id"], x["suite"], x["document"]) for x in lines} == {(f"a-p{i}", "s", f"d{i}")
                                                                          for i in range(3)}
    [s] = g["scorers"].values()
    got = unit_tests.summarize(lines)
    assert (got["headline"], got["families"]) == (s["scored"]["headline"], s["scored"]["families"])
    assert list(got["families"]) == ["text", "layout"]


def test_a_limited_run_is_its_own_run_graded_over_its_own_pages(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data"))
    one = (g := b.run(Alpha(), tmp_path / "runs", limit=1))["run"]
    [s] = g["scorers"].values()
    assert (s["rows"], s["headline"]) == (1, 0.5) and "partial" not in s
    whole = b.run(Alpha(), tmp_path / "runs")["run"]
    assert whole != one, "another choice of pages is another folder"


def test_an_unfinished_run_is_refused_unless_graded_partial(tmp_path, capsys):
    data = dataset(tmp_path / "data")
    name = benchmark.default(data).run(Alpha(), tmp_path / "runs")["run"]
    run = tmp_path / "runs" / name
    for d in ("records", "predictions"): (run / d / "a-p2.json").unlink()
    err = raised(["grade", str(run)])
    assert "isn't finished" in err and "a-p2" in err and "--partial" in err, err
    assert cli.main(["grade", str(run), "--partial"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert s["partial"] == {"no_answer": 1, "not_scored": 0, "e.g.": ["a-p2"]}, s
    assert s["headline"] == 0.5 * 2 / 3, s


def test_opb_grade_grades_a_folder_of_your_own(tmp_path, capsys):
    data = dataset(tmp_path / "data", 2)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"pages": [{"html": "<p>alpha</p>"}]}))
    assert "a-p1" in raised(["grade", str(mine), "--dataset", data]), "a missing prediction is refused"
    assert cli.main(["grade", str(mine), "--dataset", data, "--partial"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert (s["rows"], s["failed"], s["headline"]) == (2, 1, 0.25), s
    assert not (mine / "settings.json").exists(), "grading writes nothing into a folder you brought"


def test_outputs_is_accepted_with_a_warning_and_ignored(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    assert cli.main([*configured("alpha", data), "--out", str(tmp_path / "runs"), "-y"]) == 0
    out, err = capsys.readouterr()
    g = json.loads(out)
    [s] = g["scorers"].values()
    assert set(s["scored"]["families"]) == {"text", "layout"} and s["options"] == {}, s
    [run] = (tmp_path / "runs").iterdir()
    for argv in (["grade", str(run), "--outputs", "blocks"], ["grade", str(run), "--unsupported", "blocks"]):
        assert cli.main(argv) == 0
        out, err = capsys.readouterr()
        [again] = json.loads(out)["scorers"].values()
        assert "is deprecated and ignored" in err, err
        assert again["scored"]["families"] == s["scored"]["families"], again
    pred, gold = tmp_path / "pred.json", tmp_path / "data" / "gold" / "a-p0.json"
    pred.write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["score", "--pred", str(pred), "--gold", str(gold), "--outputs", "html"]) == 0
    out, err = capsys.readouterr()
    assert [v["result"] for v in json.loads(out)] == ["pass", "fail"] and "ignored" in err


def test_every_page_failing_has_headline_0(tmp_path, monkeypatch):
    def refused(self, page, request, *, timeout):
        raise harness_errors.SystemFailed("bad page", status=400)

    monkeypatch.setattr(Alpha, "send", refused)
    b = benchmark.default(dataset(tmp_path / "data"))
    g = b.run(Alpha(), tmp_path / "runs")
    [s] = g["scorers"].values()
    assert (s["headline"], s["failed"], s["zeroed"], s["coverage"]) == (0.0, 3, 3, 1.0), s


@dataclasses.dataclass(frozen=True)
class Keyed(Alpha):
    name: ClassVar[str] = "keyed"
    keys: ClassVar[tuple[str, ...]] = ("OPB_TEST_KEY",)


def test_a_missing_key_is_refused_before_any_call_and_any_folder(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "keyed", Keyed)
    monkeypatch.delenv("OPB_TEST_KEY", raising=False)
    CALLS.clear()
    argv = [*configured("keyed", dataset(tmp_path / "data")), "--out", str(tmp_path / "runs"), "-y"]
    assert "export OPB_TEST_KEY=..." in raised(argv)
    assert CALLS == [] and not (tmp_path / "runs").exists()
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    err = raised(["predict", "--system", "keyed", "--page", str(pdf)])
    assert "export OPB_TEST_KEY=..." in err and CALLS == [], err


ORG_M = {"weights": "org/m", "revision": "main"}   # what the stand-in model servers serve


@dataclasses.dataclass(frozen=True)
class Served(Alpha, harness.Served):
    """A model server's adapter, at an address where nothing listens."""

    name: ClassVar[str] = "served"
    SERVE: ClassVar[str | None] = "chandra-ocr"
    base_url: str = "http://127.0.0.1:9"
    served: dict[str, Any] = dataclasses.field(default_factory=lambda: dict(ORG_M))

    def send(self, page, request, *, timeout):
        from omni_parse_bench.harness import http

        return contract.Call(http.post(f"{self.base_url}/parse", {}, harness.budget.Budget(timeout)))


def test_a_server_that_isnt_running_stops_the_run_before_any_folder(tmp_path, capsys, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{s.getsockname()[1]}"
    monkeypatch.setitem(harness.ADAPTERS, "served", Served)
    argv = [*configured("served", dataset(tmp_path / "data"), f"system.served.base_url={url}"), "--out",
            str(tmp_path / "runs"), "-y"]
    err = raised(argv, Exception)     # the connection error itself (httpx.ConnectError), with notes
    assert f"no server at {url}" in err and "providers/serve/chandra-ocr" in err, err
    assert not (tmp_path / "runs").exists()


NOW: dict[str, Any] = {}   # what the stand-in model server says it serves; {} for a server with no /served


@dataclasses.dataclass(frozen=True)
class Checked(Alpha, harness.Served):
    """Alpha, as a model we serve: its server, a stand-in, says what it serves at /served."""

    name: ClassVar[str] = "checked"
    base_url: str = "http://127.0.0.1:9"
    served: dict[str, Any] = dataclasses.field(default_factory=lambda: dict(ORG_M))


def test_how_a_model_is_served_is_its_runs_question_and_its_server_must_say_so(tmp_path, capsys, monkeypatch):
    """`served` is an option: a run records it, and another revision is another run. Before any call the
    server must say what `served` says at /served; a server that doesn't, or has no /served, is refused."""
    import json as _json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = _json.dumps(NOW).encode()
            self.send_response(200 if NOW and self.path == "/served" else 404)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args): pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}"
    monkeypatch.setitem(harness.ADAPTERS, "checked", Checked)
    data = dataset(tmp_path / "data", 1)
    argv = [*configured("checked", data, f"system.checked.base_url={url}"), "--out", str(tmp_path / "runs"),
            "-y"]
    try:
        NOW.update(weights="org/m", revision="main")
        assert cli.main(argv) == 0
        g = json.loads(capsys.readouterr().out)
        said = json.loads((tmp_path / "runs" / g["run"] / "settings.json").read_text())
        assert said["options"]["served"] == {"weights": "org/m", "revision": "main"}, said
        err = raised([*argv, "--set", "system.checked.served.revision=other"])
        assert "revision is 'main' there and 'other' in served" in err, err
        assert len(list((tmp_path / "runs").iterdir())) == 1, "a refused server makes no run folder"
        NOW.clear()
        assert "doesn't say what it serves (GET /served: HTTP 404" in raised(argv)
    finally:
        srv.shutdown()
        NOW.clear()
    assert cli.main(["init", "chandra-ocr"]) == 0
    assert "weights: datalab-to/chandra-ocr-2" in capsys.readouterr().out


def test_grading_and_checking_need_no_harness_packages(tmp_path):
    """The base install grades: no package of the [harness] extra can be imported here."""
    data = dataset(tmp_path / "data", 1)
    (mine := tmp_path / "mine" / "predictions").mkdir(parents=True)
    (mine / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    code = f"""
import sys
for m in ("httpx", "openai", "markdown_it", "pypdfium2", "PIL"): sys.modules[m] = None
from omni_parse_bench import benchmark, cli, task
assert cli.main(["check", "--dataset", {data!r}]) == 0
assert cli.main(["grade", {str(mine.parent)!r}, "--dataset", {data!r}]) == 0
assert "omni_parse_bench.harness" not in sys.modules
"""
    got = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert got.returncode == 0, got.stderr


def test_opb_version_is_the_packages(capsys):
    import importlib.metadata

    with pytest.raises(SystemExit) as e:
        cli.main(["--version"])
    version = importlib.metadata.version("omni-parse-bench")
    assert e.value.code == 0 and capsys.readouterr().out.strip() == f"opb {version}" == "opb 1.1.1"


def test_opb_help_lists_no_hidden_command_and_takes_no_abbreviation(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "SUPPRESS" not in out and "reparse" not in out
    with pytest.raises(SystemExit):
        cli.main(["run", "--conf", "x.yaml"])


def test_opb_check_says_a_dataset_is_runnable_or_names_a_missing_page(tmp_path, capsys):
    data = dataset(tmp_path / "data")
    assert cli.main(["check", "--dataset", data]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "manifest": "manifest.parquet", "pages": 3,
                                                   "suites": 1, "inputs": 3}
    (tmp_path / "data" / "pages" / "a-p1.pdf").unlink()
    assert "a-p1" in raised(["check", "--dataset", data])


def test_opb_tests_writes_every_test_with_its_page(tmp_path, capsys):
    assert cli.main(["tests", "--dataset", dataset(tmp_path / "data", 2)]) == 0
    rows = [json.loads(x) for x in capsys.readouterr().out.splitlines()]
    assert [(r["id"], r["page_id"], r["suite"], r["document"]) for r in rows] == [
        ("h0", "a-p0", "s", "d0"), ("b0", "a-p0", "s", "d0"),
        ("h1", "a-p1", "s", "d1"), ("b1", "a-p1", "s", "d1")]


def test_opb_predict_prints_the_record_and_fails_on_a_failed_page(tmp_path, capsys, monkeypatch):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    assert cli.main(["predict", "--system", "alpha", "--page", str(pdf)]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["output"] == {"pages": [{"html": "<p>alpha beta</p>"}]}
    assert rec["error"] is None and "raw" not in rec

    def refused(self, page, request, *, timeout):
        raise harness_errors.SystemFailed("bad page", status=400, body={"why": "bad"},
                                         cost=contract.Cost(usd=0.02))

    monkeypatch.setattr(Alpha, "send", refused)
    assert cli.main(["predict", "--system", "alpha", "--page", str(pdf), "--raw"]) == 1
    rec = json.loads(capsys.readouterr().out)
    assert rec["error"]["status"] == 400 and rec["raw"] == {"why": "bad"} and rec["cost"]["usd"] == 0.02
    assert rec["sent"] == [{}], "a failed page records what it asked"
    with pytest.raises(SystemExit):
        cli.main(["predict", "--system", "alpha", "--page", str(pdf), "--outputs", "tables"])
    monkeypatch.undo()
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    for options in ({}, {"alpha": {}}):
        argv = ["predict", "--system", "alpha", "--page", str(pdf), "--options", json.dumps(options)]
        assert cli.main(argv) == 0, "the bare options, or opb run's {system: options}"
        capsys.readouterr()


def test_a_403_is_the_accounts_unless_it_is_a_moderation_flag():
    assert Alpha().account_failure(harness_errors.SystemFailed("forbidden", status=403))
    assert not Alpha().account_failure(harness_errors.SystemFailed("flagged by moderation", status=403))
    assert Alpha().account_failure(harness_errors.SystemFailed("insufficient credits", status=400, body="x"))
    assert not Alpha().account_failure(harness_errors.SystemFailed("bad page", status=400))


def test_old_commands_still_work_and_say_what_replaced_them(tmp_path, capsys, monkeypatch):
    """The commands and flags from before 1.0 work as before, each with a deprecation line."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    benchmark.default(data).run(Alpha(), tmp_path / "runs")
    [folder] = (tmp_path / "runs").iterdir()
    CALLS.clear()
    assert cli.main(["reparse", str(folder)]) == 0
    assert CALLS == [] and "`opb reparse` is deprecated and will be removed in a later release; use `opb " \
        "reread`" in capsys.readouterr().err
    raised(["reparse", str(folder), "--add", "blocks"])
    capsys.readouterr()

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    assert cli.main(["predict", "--provider", "alpha", "--page", str(pdf), "--wants", "html"]) == 0
    err = capsys.readouterr().err
    assert all(f"{x} is deprecated" in err for x in ("--provider", "--wants")), err
    assert cli.main(["providers"]) == 0
    assert "`opb providers` is deprecated" in capsys.readouterr().err


def test_opb_reread_reads_a_runs_saved_answers_again(tmp_path, capsys, monkeypatch):
    """A `parse` that gave wrong outputs without raising: after the fix, `opb reread` reads the saved answers
    with no call, and grading scores them. A `parse` that raises while reading again is reported as a bug."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    monkeypatch.setattr(sys.modules[__name__], "WRONG", {"a-p0", "a-p1"})
    CALLS.clear()
    argv = [*configured("alpha", data), "--out", str(tmp_path / "runs"), "-y"]
    assert cli.main(argv) == 0
    g = json.loads(capsys.readouterr().out)
    [s] = g["scorers"].values()
    assert (s["failed"], s["headline"]) == (0, 0.0), s
    [run] = (tmp_path / "runs").iterdir()
    WRONG.clear()
    CALLS.clear()
    assert cli.main(["reread", str(run)]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == {run.name: {"changed": 2}} and f"opb grade {run}" in err and CALLS == []
    assert cli.main(["grade", str(run)]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert (s["failed"], s["coverage"], s["headline"]) == (0, 1.0, 0.5), s
    BROKEN.add("a-p0")
    with pytest.raises(KeyError) as got:
        cli.main(["reread", str(run)])
    assert got.value.__notes__ == ["Alpha raised this while reading the answer of a-p0"], got.value.__notes__
    BROKEN.clear()
    assert "no predictions/ folder" in raised(["reread", str(tmp_path / "data")])


def test_a_bug_in_parse_stops_the_run_and_resuming_reads_it_again(tmp_path, capsys, monkeypatch):
    """A KeyError in `parse` is a bug: the run stops with its traceback, the answer is kept unread, and after
    the fix resuming the run reads it with no call."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    monkeypatch.setattr(sys.modules[__name__], "BROKEN", {"a-p0"})
    argv = [*configured("alpha", dataset(tmp_path / "data", 1)), "--out", str(tmp_path / "runs"), "-y"]
    CALLS.clear()
    with pytest.raises(KeyError) as got:
        cli.main(argv)
    assert "Alpha raised this while reading the answer of a-p0" in got.value.__notes__[0], got.value.__notes__
    [run] = (tmp_path / "runs").iterdir()
    rec = json.loads((run / "records" / "a-p0.json").read_text())
    assert (rec["unread"], rec["error"], rec["output"]) == (True, None, None)
    assert rec["raw"][0][0]["raw"]["page"] == "a-p0", "the answer is kept"
    assert not (run / "predictions" / "a-p0.json").exists() and CALLS == ["a-p0"]
    BROKEN.clear()
    CALLS.clear()
    assert cli.main(["resume", str(run), "-y"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert CALLS == [] and (s["failed"], s["headline"]) == (0, 0.5), s
    assert "unread" not in json.loads((run / "records" / "a-p0.json").read_text())
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    BROKEN.add("p")
    with pytest.raises(KeyError) as got:
        cli.main(["predict", "--system", "alpha", "--page", str(pdf)])
    notes = got.value.__notes__
    assert notes == [f"Alpha raised this while reading the answer of {pdf}"], notes


def test_a_parse_raising_system_failed_counts_the_page_0_as_unreadable(tmp_path, monkeypatch):
    def parse(self, raw, request):
        raise harness_errors.SystemFailed("the answer holds no page", status=200)

    monkeypatch.setattr(Alpha, "parse", parse)
    b = benchmark.default(dataset(tmp_path / "data", 2))
    name = (g := b.run(Alpha(), tmp_path / "runs"))["run"]
    [s] = g["scorers"].values()
    assert (s["failed"], s["zeroed"], s["coverage"], s["headline"]) == (2, 2, 1.0, 0.0), s
    err = json.loads((tmp_path / "runs" / name / "records" / "a-p0.json").read_text())["error"]
    assert err["type"] == "Unreadable" and "the answer holds no page" in err["message"]
    assert "in parse" in err["traceback"], err


def test_an_unexpected_exception_in_prediction_stops_grading(tmp_path, monkeypatch):
    """`UnitTests.prediction` raising anything but `SystemFailed` is a bug in the scorer, not a page at 0."""

    from omni_parse_bench.scorers import unit_tests

    b = benchmark.default(dataset(tmp_path / "data", 2))
    name = b.run(Alpha(), tmp_path / "runs")["run"]

    def prediction(self, output):
        raise KeyError("html")

    monkeypatch.setattr(unit_tests.UnitTests, "prediction", prediction)
    with pytest.raises(KeyError) as got:
        b.grade(tmp_path / "runs" / name)
    assert "UnitTests raised this while reading the prediction" in got.value.__notes__[0], got.value.__notes__


def test_a_prediction_that_isnt_an_object_counts_0_with_its_traceback(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data", 2))
    name = b.run(Alpha(), tmp_path / "runs")["run"]
    run = tmp_path / "runs" / name
    (run / "predictions" / "a-p0.json").write_text("[]")
    [s] = b.grade(run)["scorers"].values()
    assert (s["failed"], s["zeroed"], s["coverage"]) == (1, 1, 1.0), s
    assert s["scored"]["families"]["text"]["tests"] == 2 and s["headline"] == 0.25, s
    lines = (run / b.scorers[0].folder_name / "scores.jsonl").read_text().splitlines()
    line = next(x for x in map(json.loads, lines) if x["id"] == "a-p0")
    assert "a row is one page" in line["error"] and "in prediction" in line["traceback"], line
    for page in ("a-p0", "a-p1"):     # a failed page's details and a scored page's both say which page
        details = (run / b.scorers[0].folder_name / "details" / f"{page}.jsonl").read_text().splitlines()
        assert all(json.loads(x)["page_id"] == page and "document" in json.loads(x) for x in details), details


@pytest.mark.parametrize("answer", ["n\n", ""])
def test_no_or_ctrl_d_at_the_prompt_runs_nothing(tmp_path, capsys, monkeypatch, answer):
    import io

    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    monkeypatch.setattr(sys, "stdin", io.StringIO(answer))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    CALLS.clear()
    argv = [*configured("alpha", dataset(tmp_path / "data", 1)), "--out", str(tmp_path / "runs")]
    assert cli.main(argv) == 1
    err = capsys.readouterr().err
    assert err.rstrip().endswith("opb run: not run") and "Traceback" not in err and CALLS == [], err


def test_opb_run_help_shows_the_config_as_required(capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "--config YAML" in out and "[--config" not in out and "[--set PATH=VALUE]" in out, out


@dataclasses.dataclass(frozen=True)
class Crashes(Alpha):
    name: ClassVar[str] = "crashes"

    def send(self, page, request, *, timeout):
        raise ZeroDivisionError("oops")


def test_opb_predict_raises_a_crash_as_it_is(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "crashes", Crashes)
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    with pytest.raises(ZeroDivisionError) as got:
        cli.main(["predict", "--system", "crashes", "--page", str(pdf)])
    assert got.value.__notes__[0].startswith("Crashes raised this while predicting"), got.value.__notes__


@dataclasses.dataclass(frozen=True)
class Tagged(Alpha):
    name: ClassVar[str] = "tagged"
    tag: str = "x"


def test_opb_init_writes_a_config_and_a_run_folder_keeps_it(tmp_path, capsys, monkeypatch):
    """`opb init` writes every option at its default; `--set` changes one; the run folder's config.yaml, given
    back, asks the same question."""
    monkeypatch.setitem(harness.ADAPTERS, "tagged", Tagged)
    data = dataset(tmp_path / "data", 1)
    assert cli.main(["init", "tagged"]) == 0
    said = capsys.readouterr().out
    (c := tmp_path / "tagged.yaml").write_text(said.replace(opb_data.DEFAULT_DATASET, data))
    assert "tag: x" in c.read_text() and "timeout: 900.0" in c.read_text()
    argv = ["run", "--config", str(c), "--out", str(tmp_path / "runs"), "-y"]
    assert cli.main([*argv, "--set", "system.tagged.tag=y", "--set", "workers=2"]) == 0
    out, err = capsys.readouterr()
    g = json.loads(out)
    assert set(g) == {"run", "cost", "scorers"} and "2 at a time" in err, (g, err)
    said = json.loads((tmp_path / "runs" / g["run"] / "settings.json").read_text())
    assert said["options"] == {"tag": "y"}, said
    kept = tmp_path / "runs" / g["run"] / "config.yaml"
    assert cli.main(["resume", str(kept.parent), "-y", "--set", "timeout=60", "--retry-failed"]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out)["run"] == g["run"] and "nothing to predict" in err, "the same question"
    assert "differs in options" in raised(["resume", str(kept.parent), "-y", "--set", "system.tagged.tag=z"])
    assert "has no config.yaml" in raised(["resume", str(tmp_path), "-y"])
    assert "did you mean system.tagged.tag?" in raised([*argv, "--set", "system.tagged.tga=y"])
    assert "workers:" in raised([*argv, "--set", "workers=two"])


def test_a_page_with_no_suite_is_in_other():
    from pathlib import Path

    from omni_parse_bench import data

    row = {"page_id": "p1", "document": "d", "outputs": ["html"], "doc_path": Path("pages/p1.pdf"),
           "gt_path": Path("gold/p1.json"), "extra": {}}
    assert data.page(row).suite == data.NO_SUITE == "other"
    assert data.page(row | {"extra": {"suite": "  "}}).suite == "other"
    assert data.page(row | {"extra": {"suite": "tables", "lang": "en"}}).suite == "tables"
    assert data.page(row | {"extra": {"suite": "tables", "lang": "en"}}).extra == {"lang": "en"}
    with pytest.raises(ValueError, match="suite must be a string"):
        data.page(row | {"extra": {"suite": 3}})


def test_a_page_may_ask_for_markdown_but_not_an_unknown_output():
    from pathlib import Path

    from omni_parse_bench import data

    row = {"page_id": "p1", "document": "d", "outputs": ["markdown"], "doc_path": Path("pages/p1.pdf"),
           "gt_path": Path("gold/p1.json"), "extra": {}}
    assert data.page(row).outputs == ("markdown",)
    with pytest.raises(ValueError, match="outputs must be a non-empty list of distinct output types"):
        data.page(row | {"outputs": ["htlm"]})
