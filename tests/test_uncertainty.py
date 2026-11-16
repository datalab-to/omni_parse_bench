"""Intervals and paired comparison over synthetic score lines."""

import json
import random
import time

import pytest

from omni_parse_bench import cli, uncertainty


def line(document, tests, passed, *, suite="s", tag="t", family="text"):
    """A score line for a page of one document: `tests` tests, `passed` of them passed, all of one family."""
    c = {"tests": tests, "passed": passed}
    return {"id": f"{document}-p", "status": "scored", "row": {"document": document, "suite": suite},
            "tests": tests, "passed": passed, "per_family": {family: c}, "per_tag": {tag: c},
            "per_test_type": {"present": c}, "per_arg_kind": {"text": c}, "per_derivation": {}}


def together(n_docs, per_doc, p, seed=1):
    """Each document passes all its tests or none, with chance `p`."""
    rng = random.Random(seed)
    return [line(f"d{i}", per_doc, per_doc * (rng.random() < p)) for i in range(n_docs)]


def test_the_interval_holds_the_score_and_is_deterministic():
    pages = together(40, 5, 0.6)
    got = uncertainty.intervals(pages, resamples=200, seed=3)
    s = got["score"]
    assert s["low"] <= s["score"] <= s["high"] and s["tests"] == 200 and s["documents"] == 40
    assert got == uncertainty.intervals(pages, resamples=200, seed=3)
    for slice_ in ("families", "per_tag", "per_suite", "per_test_type", "per_arg_kind"):
        for e in got[slice_].values():
            assert e["low"] <= e["score"] <= e["high"]
    assert got["per_derivation"] == {} and set(got["families"]) == {"text"}


def test_more_resamples_do_not_move_the_interval_much():
    pages = together(60, 4, 0.5)
    a = uncertainty.intervals(pages, resamples=300)["score"]
    b = uncertainty.intervals(pages, resamples=3000)["score"]
    assert a["score"] == b["score"]
    assert abs(a["low"] - b["low"]) < 0.05 and abs(a["high"] - b["high"]) < 0.05


def test_documents_that_pass_together_give_a_wider_interval_than_independent_tests():
    # 30 documents of 10 tests; each document passes all or none. A bootstrap over tests would treat
    # these as 300 independent coin flips.
    pages = together(30, 10, 0.5)
    width = lambda e: e["high"] - e["low"]
    clustered = width(uncertainty.intervals(pages, resamples=500)["score"])
    one_test_each = [line(f"t{i}-{j}", 1, p["passed"] // 10) for i, p in enumerate(pages) for j in range(10)]
    independent = width(uncertainty.intervals(one_test_each, resamples=500)["score"])
    assert clustered > 2 * independent


def test_a_slice_with_no_tests_is_left_out():
    got = uncertainty.intervals(together(5, 2, 1.0), resamples=20)
    assert "per_derivation" in got and got["per_derivation"] == {}
    assert uncertainty.intervals([], resamples=5)["score"] is None


def test_a_line_without_a_document_is_refused():
    bad = {"id": "x", "row": {}, "tests": 1, "passed": 1, "per_family": {"text": {"tests": 1, "passed": 1}}}
    with pytest.raises(ValueError, match="row.document"):
        uncertainty.intervals([bad])


def test_paired_identical_runs_have_a_zero_gap_and_are_not_separable():
    pages = together(30, 3, 0.5)
    got = uncertainty.paired(pages, pages, resamples=200)
    assert got["score"]["gap"] == 0 and not got["score"]["separable"]
    assert (got["score"]["low"], got["score"]["high"]) == (0, 0)
    assert got["documents_paired"] == 30 and got["documents_unpaired"] == {"a": 0, "b": 0}
    assert not any(e["separable"] for e in got["per_tag"].values())


def test_paired_a_clearly_better_system_is_separable():
    a = [line(f"d{i}", 4, 4 if i % 10 else 3) for i in range(100)]
    b = [line(f"d{i}", 4, 2) for i in range(100)]
    got = uncertainty.paired(a, b, resamples=300)
    assert got["score"]["gap"] > 0.4 and got["score"]["separable"] and got["score"]["low"] > 0
    assert got["score"]["a"] > got["score"]["b"] and got["families"]["text"]["separable"]
    flipped = uncertainty.paired(b, a, resamples=300)
    assert flipped["score"]["gap"] == -got["score"]["gap"] and flipped["score"]["separable"]


def test_paired_uses_the_overlap_and_says_what_it_left_out():
    a = together(20, 2, 0.5, seed=1)
    b = [line(f"d{i}", 2, 1) for i in range(10, 30)]
    got = uncertainty.paired(a, b, resamples=50)
    assert got["documents_paired"] == 10 and got["documents_unpaired"] == {"a": 10, "b": 10}
    assert got["score"]["documents"] == 10


def test_paired_with_no_document_in_common_raises():
    with pytest.raises(ValueError, match="no document in common"):
        uncertainty.paired([line("x", 1, 1)], [line("y", 1, 1)])


@pytest.mark.parametrize("kw", [{"resamples": 0}, {"level": 1.0}, {"level": 0}])
def test_bad_options_raise(kw):
    with pytest.raises(ValueError):
        uncertainty.intervals(together(3, 1, 1.0), **kw)


def test_a_full_size_run_takes_seconds():
    rng = random.Random(0)
    pages = [line(f"d{i}", 9, rng.randint(0, 9), suite=f"s{i % 8}", tag=f"t{i % 40}", family=f"f{i % 6}")
             for i in range(1800)]
    start = time.perf_counter()
    uncertainty.intervals(pages, resamples=1000)
    assert time.perf_counter() - start < 60


def graded(folder, pages):
    (folder / "unit_tests").mkdir(parents=True)
    (folder / "unit_tests" / "scores.jsonl").write_text("\n".join(map(json.dumps, pages)) + "\n")
    return str(folder)


def test_the_commands_print_json(tmp_path, capsys):
    a = graded(tmp_path / "a", together(20, 2, 0.8))
    b = graded(tmp_path / "b", together(20, 2, 0.4, seed=2))
    assert cli.main(["intervals", a, "--resamples", "50", "--seed", "1", "--level", "0.9"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["interval"] == {"method": "cluster bootstrap over documents, percentile interval",
                               "level": 0.9, "resamples": 50, "seed": 1}
    assert cli.main(["compare", a, b, "--resamples", "50"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["documents_paired"] == 20 and "gap" in got["score"]


def test_a_folder_that_is_not_a_graded_run_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not a graded run"):
        cli.main(["intervals", str(tmp_path)])


def test_the_scores_are_the_summarys():
    from omni_parse_bench.scorers.unit_tests import unit_tests

    pages = [line(f"d{i}", 3, i % 4, suite=f"s{i % 3}", tag=f"t{i % 2}", family="text" if i % 2 else "tables")
             for i in range(20)]
    want, got = unit_tests._summary(pages), uncertainty.intervals(pages, resamples=10)
    assert got["score"]["score"] == pytest.approx(want["score"])
    for s in ("families", "per_tag", "per_suite", "per_test_type", "per_arg_kind", "per_derivation"):
        assert list(got[s]) == list(want[s])
        for k, e in want[s].items():
            assert got[s][k]["score"] == pytest.approx(e["score"])
            assert (got[s][k]["tests"], got[s][k]["documents"]) == (e["tests"], e["documents"])
