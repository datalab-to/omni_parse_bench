"""The whole benchmark on a small dataset made here, offline: predicting, resuming, grading, and the rules opb
adds to the core's (`outputs`, `Parse.check`).

Each page has one html test, that the page's html holds "alpha", and one blocks test, that a block labelled
text holds it. The stub system answers html only, with "alpha" in it.
"""
from __future__ import annotations

import dataclasses
import json
from typing import ClassVar

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")
pa = pytest.importorskip("pyarrow")
pq = pytest.importorskip("pyarrow.parquet")

from omni_parse_bench import benchmark, cli, errors, harness, task  # noqa: E402
from omni_parse_bench.harness import contract  # noqa: E402
from omni_parse_bench.harness import errors as harness_errors  # noqa: E402

CALLS: list[str] = []


@dataclasses.dataclass(frozen=True)
class Alpha(harness.PageAdapter):
    """Answers every page with html holding "alpha"."""

    name: ClassVar[str] = "alpha"
    SUPPORTS: ClassVar[frozenset[str]] = frozenset({"html"})

    def requests(self, wants):
        return [contract.Request(frozenset(wants), {})] if wants else []

    def send(self, page, request, *, timeout):
        CALLS.append(page.stem)
        return contract.Call({"html": "<p>alpha beta</p>"}, cost=contract.Cost(usd=0.01))

    def parse(self, raw, request):
        return {"html": raw["html"]}, {}


def dataset(root, n: int = 3) -> str:
    """`n` pages, each with an html test and a blocks test."""
    (root / "gold").mkdir(parents=True)
    (root / "pages").mkdir()
    rows = []
    for i in range(n):
        pid = f"a-p{i}"
        (root / "pages" / f"{pid}.pdf").write_bytes(b"%PDF")
        tests = [{"id": f"h{i}", "test_type": "present", "output_type": "html", "derivation": "authored",
                  "tags": [], "args": {"content": {"text": "alpha", "max_diffs": 0}}, "settings": {}},
                 {"id": f"b{i}", "test_type": "layout_kind", "output_type": "blocks",
                  "derivation": "authored", "tags": [],
                  "args": {"content": {"text": "alpha", "max_diffs": 0, "place": [[0.1, 0.1, 0.4, 0.2]]}},
                  "settings": {"kind": "text"}}]
        (root / "gold" / f"{pid}.json").write_text(json.dumps({"tests": tests}))
        rows.append({"page_id": pid, "document": f"d{i}", "suite": "s", "doc_path": f"pages/{pid}.pdf",
                     "gt_path": f"gold/{pid}.json", "outputs": ["blocks", "html"]})
    pq.write_table(pa.Table.from_pylist(rows), root / "manifest.parquet")
    return str(root)


def test_html_alone_is_predicted_graded_and_resumed(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data"), outputs=["html"])
    CALLS.clear()
    [(name, g)] = b.run([Alpha()], tmp_path / "runs").items()
    assert sorted(CALLS) == ["a-p0", "a-p1", "a-p2"]
    [s] = g["scorers"].values()
    assert s["headline"] == 1.0 and s["html"]["tests"] == 3 and "blocks" not in s, s
    assert g["cost"]["usd"] == 0.03
    CALLS.clear()
    b.run([Alpha()], tmp_path / "runs")
    assert CALLS == [], "a resumed run calls nothing"
    details = (tmp_path / "runs" / name / b.scorers[0].folder_name / "details" / "a-p0.jsonl").read_text()
    assert json.loads(details)["result"] == "pass"


def test_a_system_without_an_output_being_graded_is_refused_before_any_call(tmp_path):
    data = dataset(tmp_path / "data")
    CALLS.clear()
    with pytest.raises(errors.UsageError, match=r"alpha can't produce \['blocks'\]"):
        benchmark.default(data).plan([Alpha()], tmp_path / "runs")
    with pytest.raises(errors.UsageError, match="can't produce"):
        task.Parse().check([Alpha()], benchmark.default(data).scorers)
    assert CALLS == []
    benchmark.default(data, outputs=["html"]).plan([Alpha()], tmp_path / "runs")


def test_a_limited_run_has_no_headline_until_it_is_whole(tmp_path):
    b = benchmark.default(dataset(tmp_path / "data"), outputs=["html"])
    [g] = b.run([Alpha()], tmp_path / "runs", limit=1).values()
    [s] = g["scorers"].values()
    assert s["pending"] == 2 and s["headline"] is None


def test_opb_grade_grades_a_folder_of_your_own(tmp_path, capsys):
    data = dataset(tmp_path / "data", 2)
    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    (mine / "predictions" / "a-p0.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", data, "--outputs", "html"]) == 0
    [s] = json.loads(capsys.readouterr().out)["scorers"].values()
    assert (s["graded"], s["failed"], s["headline"]) == (2, 1, 0.5), s


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
    assert cli.main(["predict", "--provider", "alpha", "--page", str(pdf)]) == 0
    rec = json.loads(capsys.readouterr().out)
    assert rec["output"] == {"html": "<p>alpha beta</p>"} and rec["error"] is None and "raw" not in rec

    def refused(self, page, request, *, timeout):
        raise harness_errors.VendorError("bad page", status=400, raw={"why": "bad"},
                                         cost=contract.Cost(usd=0.02))

    monkeypatch.setattr(Alpha, "send", refused)
    assert cli.main(["predict", "--provider", "alpha", "--page", str(pdf), "--raw"]) == 1
    rec = json.loads(capsys.readouterr().out)
    assert rec["error"]["status"] == 400 and rec["raw"] == {"why": "bad"} and rec["cost"]["usd"] == 0.02
    assert rec["sent"] == [{}], "a failed page records what it asked"
    with pytest.raises(SystemExit):
        cli.main(["predict", "--provider", "alpha", "--page", str(pdf), "--wants", "tables"])


def test_a_403_is_the_accounts_unless_it_is_a_moderation_flag():
    assert Alpha().account_failure(harness_errors.VendorError("forbidden", status=403))
    assert not Alpha().account_failure(harness_errors.VendorError("flagged by moderation", status=403))
    assert Alpha().account_failure(harness_errors.VendorError("insufficient credits", status=400, body="x"))
    assert not Alpha().account_failure(harness_errors.VendorError("bad page", status=400))


def test_old_commands_still_work_and_say_what_replaced_them(tmp_path, capsys, monkeypatch):
    """`opb benchmark`, `--score-only`, `--unsupported` (as a flag or in settings.json) and `opb reparse` work
    as before, each with a deprecation line."""
    monkeypatch.setitem(harness.ADAPTERS, "alpha", Alpha)
    data = dataset(tmp_path / "data", 2)
    runs = str(tmp_path / "runs")
    assert cli.main(["benchmark", "--providers", "alpha", "--dataset", data, "--out", runs, "--outputs",
                     "html", "-y"]) == 0
    assert "`opb benchmark` is deprecated" in capsys.readouterr().err
    CALLS.clear()
    assert cli.main(["run", "--providers", "alpha", "--dataset", data, "--out", runs, "--outputs", "html",
                     "--score-only"]) == 0
    out, err = capsys.readouterr()
    assert CALLS == [] and "--score-only is deprecated" in err
    [g] = json.loads(out).values()
    [s] = g["scorers"].values()
    assert s["headline"] == 1.0, s

    mine = tmp_path / "mine"
    (mine / "predictions").mkdir(parents=True)
    for i in range(2):
        (mine / "predictions" / f"a-p{i}.json").write_text(json.dumps({"html": "<p>alpha</p>"}))
    assert cli.main(["grade", str(mine), "--dataset", data, "--unsupported", "blocks"]) == 0
    out, err = capsys.readouterr()
    [s] = json.loads(out)["scorers"].values()
    assert s["headline"] == 1.0 and "--unsupported is deprecated" in err, (s, err)
    settings = json.loads((mine / "settings.json").read_text())
    (mine / "settings.json").write_text(json.dumps({**settings, "unsupported": ["blocks"]}))
    assert cli.main(["grade", str(mine), "--dataset", data]) == 0
    out, err = capsys.readouterr()
    [s] = json.loads(out)["scorers"].values()
    assert s["headline"] == 1.0 and "`unsupported` in" in err, (s, err)

    [folder] = (tmp_path / "runs").iterdir()
    CALLS.clear()
    assert cli.main(["reparse", str(folder)]) == 0
    assert CALLS == [] and "`opb reparse` is deprecated" in capsys.readouterr().err
    assert cli.main(["reparse", str(folder), "--add", "blocks"]) == 1
