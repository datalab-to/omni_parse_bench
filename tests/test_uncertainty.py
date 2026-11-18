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
    s = got["headline"]
    assert s["low"] <= s["score"] <= s["high"] and s["tests"] == 200 and s["documents"] == 40
    assert got == uncertainty.intervals(pages, resamples=200, seed=3)
    for slice_ in ("families", "per_tag", "per_suite", "per_test_type", "per_arg_kind"):
        for e in got[slice_].values():
            assert e["low"] <= e["score"] <= e["high"]
    assert got["per_derivation"] == {} and set(got["families"]) == {"text"}


def test_more_resamples_do_not_move_the_interval_much():
    pages = together(60, 4, 0.5)
    a = uncertainty.intervals(pages, resamples=300)["headline"]
    b = uncertainty.intervals(pages, resamples=3000)["headline"]
    assert a["score"] == b["score"]
    assert abs(a["low"] - b["low"]) < 0.05 and abs(a["high"] - b["high"]) < 0.05


def test_documents_that_pass_together_give_a_wider_interval_than_independent_tests():
    # 30 documents of 10 tests; each document passes all or none. A bootstrap over tests would treat
    # these as 300 independent coin flips.
    pages = together(30, 10, 0.5)
    width = lambda e: e["high"] - e["low"]
    clustered = width(uncertainty.intervals(pages, resamples=500)["headline"])
    one_test_each = [line(f"t{i}-{j}", 1, p["passed"] // 10) for i, p in enumerate(pages) for j in range(10)]
    independent = width(uncertainty.intervals(one_test_each, resamples=500)["headline"])
    assert clustered > 2 * independent


def test_a_slice_with_no_tests_is_left_out():
    got = uncertainty.intervals(together(5, 2, 1.0), resamples=100)
    assert "per_derivation" in got and got["per_derivation"] == {}
    assert uncertainty.intervals([], resamples=100)["headline"] is None


def test_a_line_without_a_document_is_refused():
    bad = {"id": "x", "row": {}, "tests": 1, "passed": 1, "per_family": {"text": {"tests": 1, "passed": 1}}}
    with pytest.raises(ValueError, match="row.document"):
        uncertainty.intervals([bad])


def test_paired_identical_runs_have_a_zero_gap_and_are_not_excludes_zero():
    pages = together(30, 3, 0.5)
    got = uncertainty.paired(pages, pages, resamples=200)
    assert got["headline"]["gap"] == 0 and not got["headline"]["excludes_zero"]
    assert (got["headline"]["low"], got["headline"]["high"]) == (0, 0)
    assert got["documents_paired"] == 30 and got["documents_unpaired"] == {"a": 0, "b": 0}
    assert not any(e["excludes_zero"] for e in got["per_tag"].values())


def test_paired_a_clearly_better_system_is_excludes_zero():
    a = [line(f"d{i}", 4, 4 if i % 10 else 3) for i in range(100)]
    b = [line(f"d{i}", 4, 2) for i in range(100)]
    got = uncertainty.paired(a, b, resamples=300)
    assert got["headline"]["gap"] > 0.4 and got["headline"]["excludes_zero"] and got["headline"]["low"] > 0
    assert got["headline"]["a"] > got["headline"]["b"] and got["families"]["text"]["excludes_zero"]
    flipped = uncertainty.paired(b, a, resamples=300)
    assert flipped["headline"]["gap"] == -got["headline"]["gap"] and flipped["headline"]["excludes_zero"]


def test_paired_uses_the_overlap_and_says_what_it_left_out():
    a = together(20, 2, 0.5, seed=1)
    b = [line(f"d{i}", 2, 1) for i in range(10, 30)]
    got = uncertainty.paired(a, b, resamples=100)
    assert got["documents_paired"] == 10 and got["documents_unpaired"] == {"a": 10, "b": 10}
    assert got["headline"]["documents"] == 10


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
    assert time.perf_counter() - start < 30


def graded(folder, pages):
    (folder / "unit_tests").mkdir(parents=True)
    (folder / "unit_tests" / "scores.jsonl").write_text("\n".join(map(json.dumps, pages)) + "\n")
    return str(folder)


def test_the_commands_print_json(tmp_path, capsys):
    failed = {"id": "dz-p", "status": "failed", "cause": "system", "row": {"document": "dz", "suite": "s"},
              "tests": 2, "passed": 0, "per_family": {"text": {"tests": 2, "passed": 0}},
              "per_tag": {"t": {"tests": 2, "passed": 0}},
              "per_test_type": {"present": {"tests": 2, "passed": 0}}, "per_arg_kind": {},
              "per_derivation": {}}
    a = graded(tmp_path / "a", [*together(20, 2, 0.8), failed])
    b = graded(tmp_path / "b", [*together(20, 2, 0.4, seed=2), {**failed, "id": "dz-q"}])
    assert cli.main(["intervals", a, "--resamples", "100", "--seed", "1", "--level", "0.9"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["interval"]["level"] == 0.9 and got["interval"]["resamples"] == 100
    assert got["headline"]["draws"] == 100
    assert cli.main(["compare", a, b, "--resamples", "100"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["documents_paired"] == 21 and "gap" in got["headline"]


def test_a_folder_that_is_not_a_graded_run_is_refused(tmp_path):
    with pytest.raises(ValueError, match="not a graded run"):
        cli.main(["intervals", str(tmp_path)])


def test_the_scores_are_the_summarys():
    from omni_parse_bench.scorers.unit_tests import unit_tests

    pages = [line(f"d{i}", 3, i % 4, suite=f"s{i % 3}", tag=f"t{i % 2}", family="text" if i % 2 else "tables")
             for i in range(20)]
    want, got = unit_tests._summary(pages), uncertainty.intervals(pages, resamples=100)
    assert got["headline"]["score"] == pytest.approx(want["score"])
    for s in ("families", "per_tag", "per_suite", "per_test_type", "per_arg_kind", "per_derivation"):
        assert list(got[s]) == list(want[s])
        for k, e in want[s].items():
            assert got[s][k]["score"] == pytest.approx(e["score"])
            assert (got[s][k]["tests"], got[s][k]["documents"]) == (e["tests"], e["documents"])


def test_a_slice_of_one_or_two_documents_has_no_interval():
    pages = together(30, 3, 0.5)
    pages[0] = line("d0", 3, 3, tag="rare")
    pages[1] = line("d1", 3, 0, tag="rare2")
    pages[2] = line("d2", 3, 3, tag="rare2")
    got = uncertainty.intervals(pages, resamples=200)
    one, two = got["per_tag"]["rare"], got["per_tag"]["rare2"]
    assert (one["low"], one["high"], one["documents"]) == (None, None, 1)
    assert (two["low"], two["high"], two["documents"]) == (None, None, 2)
    assert one["draws"] < 190 and two["draws"] < 190
    other = [line(f"d{i}", 3, 0, tag="rare" if i < 2 else "t") for i in range(30)]
    cmp = uncertainty.paired(pages, other, resamples=200)["per_tag"]["rare"]
    assert cmp["low"] is None and cmp["excludes_zero"] is False


def test_a_slice_absent_from_many_draws_has_no_interval_but_a_common_one_does():
    pages = [line(f"d{i}", 2, 1, tag="t") for i in range(40)]
    pages += [line(f"e{i}", 2, 1, tag="six") for i in range(6)]   # 6 of 46 documents: absent ~ 0.1% of draws
    pages += [line(f"f{i}", 2, 1, tag="five") for i in range(5)]
    got = uncertainty.intervals(pages, resamples=300)["per_tag"]
    assert got["six"]["low"] is not None and got["six"]["draws"] >= 285
    assert got["five"]["low"] is not None   # 5 documents is enough


def test_all_documents_passing_gives_a_zero_width_interval_when_there_are_enough():
    got = uncertainty.intervals([line(f"d{i}", 2, 2) for i in range(10)], resamples=100)["headline"]
    assert (got["score"], got["low"], got["high"], got["draws"]) == (1, 1, 1, 100)


def test_the_headline_needs_every_family_in_a_draw():
    pages = [line(f"d{i}", 2, 1, family="tables") for i in range(30)]
    pages.append(line("rare", 2, 2, family="text"))     # one document holds the text family
    got = uncertainty.intervals(pages, resamples=200)
    assert got["headline"]["draws"] < 190 and got["headline"]["low"] is None
    assert got["families"]["tables"]["low"] is not None


def test_both_systems_share_each_draw():
    rng = random.Random(0)
    base = [rng.random() < 0.5 for _ in range(60)]
    a = [line(f"d{i}", 2, 2 * ok) for i, ok in enumerate(base)]
    b = [line(f"d{i}", 2, 2 * (ok if i % 10 else not ok)) for i, ok in enumerate(base)]
    got = uncertainty.paired(a, b, resamples=500)["headline"]
    ia, ib = (uncertainty.intervals(x, resamples=500)["headline"] for x in (a, b))
    # drawn independently, the gap would be as wide as the two intervals together
    independent = ((ia["high"] - ia["low"]) ** 2 + (ib["high"] - ib["low"]) ** 2) ** 0.5
    assert got["high"] - got["low"] < 0.6 * independent


def test_paired_reports_entries_and_families_only_one_system_has():
    a = [line(f"d{i}", 2, 1, tag="x", family="text") for i in range(20)]
    b = [line(f"d{i}", 2, 1, tag="y", family="tables") for i in range(20)]
    got = uncertainty.paired(a, b, resamples=100)
    assert got["headline_families"] == [] and got["headline"] is None
    assert got["entries_unpaired"]["a"] > 0 and got["entries_unpaired"]["b"] > 0
    assert got["per_tag"] == {} and got["families"] == {}
    c = [line(f"d{i}", 2, 1, tag="x", family="text") for i in range(20)]
    c += [dict(line(f"d{i}", 2, 1, tag="x", family="tables"), id=f"d{i}-q") for i in range(20)]
    got = uncertainty.paired(c, a, resamples=100)
    assert got["headline_families"] == ["text"]
    assert got["headline"]["a"] == pytest.approx(0.5) and got["entries_unpaired"] == {"a": 1, "b": 0}


def test_paired_counts_documents_whose_tests_differ():
    a = [line(f"d{i}", 2, 1) for i in range(20)]
    b = [line(f"d{i}", 3 if i < 4 else 2, 1) for i in range(20)]
    assert uncertainty.paired(a, b, resamples=100)["documents_mismatched"] == 4


def test_a_document_in_two_suites_is_one_cluster_and_counts_in_each_suite():
    pages = [line(f"d{i}", 2, 1, suite="s1") for i in range(10)]
    pages += [dict(line(f"d{i}", 2, 2, suite="s2"), id=f"d{i}-q") for i in range(10)]
    got = uncertainty.intervals(pages, resamples=100)
    assert got["headline"]["documents"] == 10 and got["headline"]["tests"] == 40
    assert got["per_suite"]["s1"]["documents"] == got["per_suite"]["s2"]["documents"] == 10


@pytest.mark.parametrize("n", [True, 100.0, "100", 99])
def test_resamples_must_be_an_integer_of_at_least_100(n):
    with pytest.raises(ValueError, match="resamples"):
        uncertainty.intervals(together(10, 1, 0.5), resamples=n)


def test_a_95_percent_interval_covers_the_truth_about_that_often():
    rng = random.Random(7)
    covered = 0
    for sim in range(200):
        pages = [line(f"d{i}", 1, rng.random() < 0.5) for i in range(50)]
        got = uncertainty.intervals(pages, resamples=200, seed=sim)["headline"]
        covered += got["low"] <= 0.5 <= got["high"]
    assert 0.90 <= covered / 200 <= 0.98, covered


def test_the_format_family_has_an_interval_beside_the_headline_and_is_not_in_it():
    """The headline is the mean of the text, tables and layout families; `format` is a family of its own."""
    text = together(40, 5, 0.8, seed=2)
    fmt = [line(f"f{i}", 4, 4 * (i % 2), family="format") for i in range(30)]
    got = uncertainty.intervals(text + fmt, resamples=100, seed=1)
    assert set(got["families"]) == {"text", "format"}
    assert got["headline"]["score"] == got["families"]["text"]["score"]    # the headline families only
    assert got["families"]["format"]["score"] == 0.5
    both = uncertainty.paired(text + fmt, text + fmt, resamples=100, seed=1)
    assert both["headline_families"] == ["text"]
    only = uncertainty.intervals(fmt, resamples=100, seed=1)   # no headline family: the mean of its own
    assert only["headline"]["score"] == 0.5
