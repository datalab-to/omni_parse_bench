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
from typing import ClassVar

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from omni_parse_bench import benchmark, cli, harness  # noqa: E402
from omni_parse_bench.harness import contract  # noqa: E402
from omni_parse_bench.harness import errors as harness_errors  # noqa: E402

CALLS: list[str] = []
WANTS: list[frozenset[str]] = []   # what each `requests` was given
BROKEN: set[str] = set()           # pages whose answer `parse` can't read


@dataclasses.dataclass(frozen=True)
class Alpha(harness.PageAdapter):
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
    assert s["families"] == {"text": {"score": 1.0, "tests": 3, "documents": 3},
                             "layout": {"score": 0.0, "tests": 3, "documents": 3}}, s
    assert (s["headline"], s["coverage"], s["failed"]) == (0.5, 1.0, 0), "no blocks: layout 0, not a failure"
    assert s["headline_is"] == "the mean of the families' scores × coverage" and "partial" not in s
    assert g["cost"]["usd"] == 0.03
    CALLS.clear()
    b.run(Alpha(), tmp_path / "runs")
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
    assert (rec["output"], rec["error"], rec["cost"]["usd"]) == ({}, None, None), rec
    [s] = g["scorers"].values()
    assert (s["coverage"], s["failed"], s["rows"]) == (1.0, 0, 3), "not a failed page: coverage stays 1"
    assert s["families"]["layout"] == {"score": 0.0, "tests": 3, "documents": 3}, s


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
    assert (got["headline"], got["families"]) == (s["headline"], s["families"])
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
    assert cli.main(["grade", str(run)]) == 1
    err = capsys.readouterr().err
    assert "isn't finished" in err and "a-p2" in err and "--partial" in err, err
    assert cli.main(["grade", str(run), "--partial"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert s["partial"] == {"no_answer": ["a-p2"], "not_scored": []} and s["headline"] == 0.5 * 2 / 3, s


def test_opb_grade_grades_a_folder_of_your_own(tmp_path, capsys):
    data = dataset(tmp_path / "data", 2)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", data]) == 1
    assert "a-p1" in capsys.readouterr().err, "a missing prediction is refused"
    assert cli.main(["grade", str(mine), "--dataset", data, "--partial"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert (s["rows"], s["failed"], s["headline"]) == (2, 1, 0.25), s
    assert not (mine / "settings.json").exists(), "grading writes nothing into a folder you brought"


def test_outputs_is_accepted_with_a_warning_and_ignored(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    assert cli.main(["run", "--system", "alpha", "--dataset", data, "--out", str(tmp_path / "runs"),
                     "--outputs", "html", "-y"]) == 0
    out, err = capsys.readouterr()
    assert "opb: --outputs is deprecated and ignored: each page asks for the outputs its tests read" in err
    g = json.loads(out)
    [s] = g["scorers"].values()
    assert set(s["families"]) == {"text", "layout"} and s["options"] == {}, s
    [run] = (tmp_path / "runs").iterdir()
    for argv in (["grade", str(run), "--outputs", "blocks"], ["grade", str(run), "--unsupported", "blocks"]):
        assert cli.main(argv) == 0
        out, err = capsys.readouterr()
        [again] = json.loads(out)["scorers"].values()
        assert "is deprecated and ignored" in err and again["families"] == s["families"], (again, err)
    pred, gold = tmp_path / "pred.json", tmp_path / "data" / "gold" / "a-p0.json"
    pred.write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["score", "--pred", str(pred), "--gold", str(gold), "--outputs", "html"]) == 0
    out, err = capsys.readouterr()
    assert [v["result"] for v in json.loads(out)] == ["pass", "fail"] and "ignored" in err


def test_every_page_failing_has_headline_0(tmp_path, monkeypatch):
    def refused(self, page, request, *, timeout):
        raise harness_errors.VendorError("bad page", status=400)

    monkeypatch.setattr(Alpha, "send", refused)
    b = benchmark.default(dataset(tmp_path / "data"))
    g = b.run(Alpha(), tmp_path / "runs")
    [s] = g["scorers"].values()
    assert (s["headline"], s["failed"], s["coverage"]) == (0.0, 3, 0.0), s


@dataclasses.dataclass(frozen=True)
class Keyed(Alpha):
    name: ClassVar[str] = "keyed"
    keys: ClassVar[tuple[str, ...]] = ("OPB_TEST_KEY",)


def test_a_missing_key_is_refused_before_any_call_and_any_folder(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "keyed", Keyed)
    monkeypatch.delenv("OPB_TEST_KEY", raising=False)
    CALLS.clear()
    argv = ["run", "--system", "keyed", "--dataset", dataset(tmp_path / "data"), "--out",
            str(tmp_path / "runs"), "-y"]
    assert cli.main(argv) == 1
    assert "export OPB_TEST_KEY=..." in capsys.readouterr().err
    assert CALLS == [] and not (tmp_path / "runs").exists()
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    assert cli.main(["predict", "--system", "keyed", "--page", str(pdf)]) == 1
    assert "export OPB_TEST_KEY=..." in capsys.readouterr().err and CALLS == []


@dataclasses.dataclass(frozen=True)
class Served(Alpha):
    """A model server's adapter, at an address where nothing listens."""

    name: ClassVar[str] = "served"
    SERVE: ClassVar[str | None] = "chandra"
    base_url: str = "http://127.0.0.1:9"

    def send(self, page, request, *, timeout):
        from omni_parse_bench.harness import http

        return contract.Call(http.post(f"{self.base_url}/parse", {}, harness.budget.Budget(timeout)))


def test_a_server_that_isnt_running_stops_the_run_with_nothing_recorded(tmp_path, capsys, monkeypatch):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{s.getsockname()[1]}"
    monkeypatch.setitem(harness.ADAPTERS, "served", Served)
    argv = ["run", "--system", "served", "--options", json.dumps({"base_url": url}), "--dataset",
            dataset(tmp_path / "data"), "--out", str(tmp_path / "runs"), "-y"]
    assert cli.main(argv) == 1
    out, err = capsys.readouterr()
    assert f"no server at {url}" in err and "providers/serve/chandra" in err and out == "", (out, err)
    assert err.rstrip().endswith("then run the same command again") and "rerun" not in err, err
    [run] = (tmp_path / "runs").iterdir()
    assert list((run / "records").iterdir()) == []


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
    assert e.value.code == 0 and capsys.readouterr().out.strip() == f"opb {version}" == "opb 1.0.0"


def test_opb_help_lists_no_hidden_command_and_takes_no_abbreviation(capsys):
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = capsys.readouterr().out
    assert "SUPPRESS" not in out and "reparse" not in out
    with pytest.raises(SystemExit):
        cli.main(["run", "--sys", "alpha"])


def test_opb_check_says_a_dataset_is_runnable_or_names_a_missing_page(tmp_path, capsys):
    data = dataset(tmp_path / "data")
    assert cli.main(["check", "--dataset", data]) == 0
    assert json.loads(capsys.readouterr().out) == {"ok": True, "manifest": "manifest.parquet", "pages": 3,
                                                   "suites": 1, "inputs": 3}
    (tmp_path / "data" / "pages" / "a-p1.pdf").unlink()
    assert cli.main(["check", "--dataset", data]) == 1
    assert "a-p1" in capsys.readouterr().err


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
    assert rec["output"] == {"html": "<p>alpha beta</p>"} and rec["error"] is None and "raw" not in rec

    def refused(self, page, request, *, timeout):
        raise harness_errors.VendorError("bad page", status=400, raw={"why": "bad"},
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
    assert Alpha().account_failure(harness_errors.VendorError("forbidden", status=403))
    assert not Alpha().account_failure(harness_errors.VendorError("flagged by moderation", status=403))
    assert Alpha().account_failure(harness_errors.VendorError("insufficient credits", status=400, body="x"))
    assert not Alpha().account_failure(harness_errors.VendorError("bad page", status=400))


def test_old_commands_still_work_and_say_what_replaced_them(tmp_path, capsys, monkeypatch):
    """The commands and flags from before 1.0 work as before, each with a deprecation line."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    runs = str(tmp_path / "runs")
    assert cli.main(["benchmark", "--providers", "alpha", "--dataset", data, "--out", runs, "-y"]) == 0
    assert "`opb benchmark` is deprecated" in capsys.readouterr().err
    CALLS.clear()
    assert cli.main(["run", "--providers", "alpha", "--dataset", data, "--out", runs, "--score-only"]) == 0
    out, err = capsys.readouterr()
    assert CALLS == [] and "--score-only is deprecated" in err
    [g] = json.loads(out).values()
    [s] = g["scorers"].values()
    assert s["headline"] == 0.5, s

    [folder] = (tmp_path / "runs").iterdir()
    CALLS.clear()
    assert cli.main(["reparse", str(folder)]) == 0
    assert CALLS == [] and "`opb reparse` is deprecated and will be removed in a later release; use `opb " \
        "reread`" in capsys.readouterr().err
    assert cli.main(["reparse", str(folder), "--add", "blocks"]) == 1
    capsys.readouterr()

    (tmp_path / "ids.txt").write_text("a-p0\n")
    assert cli.main(["run", "--providers", "alpha", "--dataset", data, "--out", str(tmp_path / "old"),
                     "--pages", str(tmp_path / "ids.txt"), "-y"]) == 0
    err = capsys.readouterr().err
    assert all(f"{x} is deprecated" in err for x in ("--providers", "--pages")), err
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    assert cli.main(["predict", "--provider", "alpha", "--page", str(pdf), "--wants", "html"]) == 0
    err = capsys.readouterr().err
    assert all(f"{x} is deprecated" in err for x in ("--provider", "--wants")), err
    assert cli.main(["providers"]) == 0
    assert "`opb providers` is deprecated" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main(["run", "--providers", "alpha", "--systems", "alpha", "--dataset", data, "-y"])
    assert "not allowed with argument" in capsys.readouterr().err


def test_opb_reread_reads_a_runs_saved_answers_again(tmp_path, capsys, monkeypatch):
    """A bug in `parse` records the pages as unreadable (counted 0); after the fix, `opb reread` reads the
    saved answers with no call, and grading scores them."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    monkeypatch.setattr(sys.modules[__name__], "BROKEN", {"a-p0", "a-p1"})
    CALLS.clear()
    argv = ["run", "--system", "alpha", "--dataset", data, "--out", str(tmp_path / "runs"), "-y"]
    assert cli.main(argv) == 0
    g = json.loads(capsys.readouterr().out)
    [s] = g["scorers"].values()
    assert (s["failed"], s["headline"]) == (2, 0.0), s
    [run] = (tmp_path / "runs").iterdir()
    assert json.loads((run / "records" / "a-p0.json").read_text())["error"]["type"] == "ReadError"
    BROKEN.clear()
    CALLS.clear()
    assert cli.main(["reread", str(run)]) == 0
    out, err = capsys.readouterr()
    assert json.loads(out) == {run.name: {"changed": 2}} and f"opb grade {run}" in err and CALLS == []
    assert cli.main(["grade", str(run)]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert (s["failed"], s["coverage"], s["headline"]) == (0, 1.0, 0.5), s
    assert cli.main(["reread", str(tmp_path / "data")]) == 1
    assert "no predictions/ folder" in capsys.readouterr().err


@pytest.mark.parametrize("answer", ["n\n", ""])
def test_no_or_ctrl_d_at_the_prompt_runs_nothing(tmp_path, capsys, monkeypatch, answer):
    import io

    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    monkeypatch.setattr(sys, "stdin", io.StringIO(answer))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    CALLS.clear()
    assert cli.main(["run", "--system", "alpha", "--dataset", dataset(tmp_path / "data", 1), "--out",
                     str(tmp_path / "runs")]) == 1
    err = capsys.readouterr().err
    assert err.rstrip().endswith("opb run: not run") and "Traceback" not in err and CALLS == [], err


def test_opb_run_help_shows_defaults_and_system_as_required(capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "seconds per page (default: 900)" in out and "(default: the system's own)" in out, out
    assert "--system NAME" in out and "[--system" not in out and "--systems" not in out, out


@dataclasses.dataclass(frozen=True)
class Crashes(Alpha):
    name: ClassVar[str] = "crashes"

    def send(self, page, request, *, timeout):
        raise ZeroDivisionError("oops")


def test_opb_predict_says_whose_bug_a_crash_is(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "crashes", Crashes)
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    assert cli.main(["predict", "--system", "crashes", "--page", str(pdf)]) == 1
    err = capsys.readouterr().err
    assert "Bug: Crashes raised ZeroDivisionError while predicting" in err and "this is a bug in" in err, err


def test_deprecated_systems_runs_each_and_one_stopping_doesnt_stop_the_next(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    monkeypatch.setitem(harness.ADAPTERS, "crashes", Crashes)
    CALLS.clear()
    argv = ["run", "--systems", "crashes", "alpha", "--options", json.dumps({"alpha": [{}]}), "--dataset",
            dataset(tmp_path / "data", 1), "--out", str(tmp_path / "runs"), "--workers", "1", "-y"]
    assert cli.main(argv) == 1
    out, err = capsys.readouterr()
    assert "--systems is deprecated" in err and "use `--system NAME`, one system per command" in err, err
    assert "opb run: crashes: Bug: Crashes raised ZeroDivisionError" in err, err
    [(name, g)] = json.loads(out).items()
    assert name == g["run"] and name.startswith("alpha") and CALLS == ["a-p0"], (out, CALLS)
    assert {p.name.split("-")[0] for p in (tmp_path / "runs").iterdir()} == {"alpha", "crashes"}


@dataclasses.dataclass(frozen=True)
class Tagged(Alpha):
    name: ClassVar[str] = "tagged"
    tag: str = "x"


def test_opb_run_takes_one_system_and_its_bare_options(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "tagged", Tagged)
    data = dataset(tmp_path / "data", 1)
    argv = ["run", "--system", "tagged", "--dataset", data, "--out", str(tmp_path / "runs"), "-y"]
    assert cli.main([*argv, "--options", '{"tag": "y"}']) == 0
    out, err = capsys.readouterr()
    g = json.loads(out)
    assert set(g) == {"run", "cost", "scorers"} and "deprecated" not in err, (g, err)
    said = json.loads((tmp_path / "runs" / g["run"] / "settings.json").read_text())
    assert said["options"] == {"tag": "y"}, said
    assert cli.main([*argv, "--options", '{"tagged": {"tag": "y"}}']) == 0
    assert json.loads(capsys.readouterr().out)["run"] == g["run"], "the keyed shape is the same run"
    with pytest.raises(SystemExit):
        cli.main(["run", "--system", "tagged", "alpha", "--dataset", data])
    assert "unrecognized arguments: alpha" in capsys.readouterr().err


def test_opb_run_workers_is_one_number(tmp_path, capsys, monkeypatch):
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    argv = ["run", "--system", "alpha", "--dataset", dataset(tmp_path / "data", 1), "--out",
            str(tmp_path / "runs"), "-y"]
    assert cli.main([*argv, "--workers", "2"]) == 0
    assert "2 at a time" in capsys.readouterr().err
    with pytest.raises(SystemExit):
        cli.main([*argv, "--workers", '{"alpha": 2}'])
    assert "invalid int value" in capsys.readouterr().err
