"""The summary's effective documents, and its marker for keys that select the same tests."""

import random
import subprocess
import sys

import pytest

from omni_parse_bench import pooling
from omni_parse_bench.scorers import unit_tests
from omni_parse_bench.scorers.unit_tests import unit_tests as scorer


def line(test_id, *, document="d", page=None, suite="s", tags=(), derivation="authored", ok=True,
         test_type="present"):
    """A test line, as `lines` writes it, for `summarize`."""
    return {"page_id": page or document, "document": document, "suite": suite, "test_id": test_id,
            "test_type": test_type, "derivation": derivation, "tags": list(tags),
            "result": "pass" if ok else "fail",
            "args": {"content": {"text": test_id, "max_diffs": 0}}}


def test_effective_documents_on_small_known_examples():
    assert pooling.effective_documents([4, 4, 4]) == 3
    assert pooling.effective_documents([3, 1]) == pytest.approx(1.6)
    assert pooling.effective_documents([]) == 0


def test_every_entry_has_effective_documents_equal_to_documents_for_equal_documents():
    xs = [line(f"t{i}", document=f"d{i // 2}", tags=["a"]) for i in range(8)]     # 4 documents of 2 tests
    s = unit_tests.summarize(xs)
    for entry in (s["families"]["text"], s["per_tag"]["a"], s["per_suite"]["s"],
                  s["per_test_type"]["present"], s["per_derivation"]["authored"], s["per_arg_kind"]["text"]):
        assert (entry["documents"], entry["effective_documents"]) == (4, 4.0), entry


def test_effective_documents_is_smaller_for_skewed_documents_and_sums_a_documents_pages():
    xs = [line("a1", document="d1", page="p1"), line("a2", document="d1", page="p2"),
          line("a3", document="d1", page="p2"), line("b1", document="d2")]
    got = unit_tests.summarize(xs)["families"]["text"]
    assert got["documents"] == 2
    assert got["effective_documents"] == 1.6     # d1 holds 3 tests, d2 holds 1: 16 / 10


def test_a_summary_keeps_its_scores_next_to_the_new_keys():
    xs = [line("a", ok=True, tags=["x"]), line("b", ok=False, tags=["x"])]
    s = unit_tests.summarize(xs)
    assert s["score"] == 0.5 and s["families"]["text"]["score"] == 0.5 and s["per_tag"]["x"]["score"] == 0.5


def test_keys_with_identical_tests_are_twins_and_entries_without_twins_have_no_marker():
    xs = [line("a", tags=["rus", "Cyrl"]), line("b", tags=["rus", "Cyrl"], ok=False),
          line("c", tags=["lone"])]
    tags = unit_tests.summarize(xs)["per_tag"]
    assert tags["rus"]["same_tests_as"] == ["Cyrl"] and tags["Cyrl"]["same_tests_as"] == ["rus"]
    assert "same_tests_as" not in tags["lone"]


def test_equal_counts_with_different_tests_are_not_twins():
    xs = [line("a", tags=["x"]), line("b", tags=["y"])]       # one test each, different ids
    tags = unit_tests.summarize(xs)["per_tag"]
    assert (tags["x"]["tests"], tags["x"]["score"]) == (tags["y"]["tests"], tags["y"]["score"])
    assert "same_tests_as" not in tags["x"] and "same_tests_as" not in tags["y"]


def test_three_way_twins_list_the_other_two_sorted():
    xs = [line("a", tags=["c", "a", "b"]), line("b", tags=["a", "b", "c"])]
    tags = unit_tests.summarize(xs)["per_tag"]
    assert tags["a"]["same_tests_as"] == ["b", "c"] and tags["c"]["same_tests_as"] == ["a", "b"]


def test_arg_kinds_can_be_twins_and_families_never_carry_the_marker():
    mixed = {"x": {"latex": "x"}, "y": {"number": "1"}}          # one test, counted under number and latex
    xs = [{**line("a"), "args": mixed}, line("b")]
    s = unit_tests.summarize(xs)
    assert s["per_arg_kind"]["number"]["same_tests_as"] == ["latex"]
    assert s["per_arg_kind"]["latex"]["same_tests_as"] == ["number"]
    assert "same_tests_as" not in s["per_arg_kind"]["text"]
    assert all("same_tests_as" not in e for e in s["families"].values())


def score_line(document, per_tag, *, ids=True, page_ids=5, suite="s"):
    """A score line for `summarize` from `{tag: (tests, passed, digest)}`, one test family, with the
    page-level `ids` when `page_ids` is not None and each tag's digest when `ids`."""
    tags = {k: {"tests": t, "passed": p, **({"ids": d} if ids else {})} for k, (t, p, d) in per_tag.items()}
    n = max((t for t, _, _ in per_tag.values()), default=1)
    return {"id": document, "row": {"document": document, "suite": suite}, "tests": n, "passed": n,
            **({"ids": page_ids} if page_ids is not None else {}),
            "per_family": {"text": {"tests": n, "passed": n}}, "per_tag": tags, "per_test_type": {},
            "per_arg_kind": {}, "per_derivation": {}}


def test_twin_tags_by_digest_across_score_lines():
    a = score_line("d1", {"x": (1, 1, 3), "y": (1, 1, 3)})
    b = score_line("d2", {"x": (1, 1, 4), "y": (1, 1, 4)})
    s = scorer._summary([a, b])
    assert s["per_tag"]["x"]["same_tests_as"] == ["y"]
    c = score_line("d2", {"x": (1, 1, 4), "y": (1, 1, 5)})
    assert "same_tests_as" not in scorer._summary([a, c])["per_tag"]["x"]


def test_only_tags_and_arg_kinds_can_have_twins():
    s = scorer._summary([score_line("d", {"x": (1, 1, 3)})])
    for kind in ("families", "per_suite", "per_test_type", "per_derivation"):
        assert all("same_tests_as" not in e for e in s[kind].values())
    xs = [line("a", suite="s1", derivation="D"), line("b", suite="s2", derivation="D")]
    s = unit_tests.summarize(xs)
    assert all("same_tests_as" not in e for kind in ("per_suite", "per_derivation", "per_test_type")
               for e in s[kind].values())


def test_lines_graded_before_the_digest_make_no_twins_and_do_not_crash():
    new = score_line("d1", {"x": (1, 1, 3), "y": (1, 1, 3)})
    old = score_line("d2", {"x": (1, 1, 0), "y": (1, 1, 0)}, ids=False, page_ids=None)
    assert "same_tests_as" in scorer._summary([new])["per_tag"]["x"]
    for pages in ([old], [new, old], [old, new]):
        s = scorer._summary(pages)
        assert "same_tests_as" not in s["per_tag"]["x"]
        assert s["per_tag"]["x"]["tests"] == len(pages)


def test_an_old_page_that_recorded_no_tags_cannot_make_false_twins_next_to_new_pages():
    new = score_line("d1", {"B": (1, 1, 7), "C": (1, 1, 7)})   # one test carrying both tags
    old = {k: v for k, v in score_line("d2", {}, ids=False, page_ids=None).items()}
    s = scorer._summary([new, old])        # the old page may hold a B test it did not record
    assert "same_tests_as" not in s["per_tag"]["B"] and "same_tests_as" not in s["per_tag"]["C"]


def test_a_key_without_a_digest_on_one_page_is_not_a_twin_but_others_still_are():
    page = score_line("d1", {"A": (1, 1, 7), "C": (1, 1, 7), "B": (1, 1, 7)})
    del page["per_tag"]["B"]["ids"]
    s = scorer._summary([page])["per_tag"]
    assert s["A"]["same_tests_as"] == ["C"] and s["C"]["same_tests_as"] == ["A"]
    assert "same_tests_as" not in s["B"]


def test_a_duplicate_test_id_on_a_page_counts_twice_like_a_multiset():
    xs = [line("a", tags=["x", "y"]), line("a", tags=["x", "y"]), line("a", tags=["z"]),
          line("b", tags=["z"])]
    tags = unit_tests.summarize(xs)["per_tag"]
    assert tags["x"]["same_tests_as"] == ["y"]       # {a, a} twice over: the counts and digests agree
    assert "same_tests_as" not in tags["z"]          # {a, b} is not {a, a}


def test_ids_that_are_not_ascii_or_a_lone_surrogate_still_encode():
    assert scorer._ids(["é", "日本語"]) == scorer._ids(["日本語", "é"])
    assert scorer._ids(["\ud800"]) != scorer._ids(["\ud801"])
    xs = [line("\ud800", tags=["x", "y"]), line("é", tags=["x", "y"])]
    assert unit_tests.summarize(xs)["per_tag"]["x"]["same_tests_as"] == ["y"]


def test_a_count_with_a_test_without_an_id_has_no_digests():
    mark = (True, "present", "authored", ["x"], ["text"])
    marks = [(*mark, "a"), (*mark, None)]
    got = scorer._count(marks)
    assert all("ids" not in c for k in got.values() for c in k.values())
    with_id = scorer._count([(*mark, "a")])
    assert "ids" in with_id["per_tag"]["x"] and "ids" in with_id["per_arg_kind"]["text"]
    assert "ids" not in with_id["per_family"]["text"] and "ids" not in with_id["per_test_type"]["present"]
    assert "ids" not in with_id["per_derivation"]["authored"]


def test_a_failed_page_keeps_a_twin_pair_a_twin_pair():
    from tests.test_scorer import on_one_page, text
    tests = on_one_page({"id": "a", "test_type": "present", "tags": ["rus", "Cyrl"], "args": text("x")},
                        {"id": "b", "test_type": "present", "tags": ["rus", "Cyrl"], "args": text("y")})
    ok = scorer.UnitTests().score({"html": "<p>x y</p>"}, tests)
    failed = scorer.UnitTests().score_failure(tests)
    for res in (ok, failed):
        ln = {"id": "p", "row": {"document": "d", "suite": "s"}, **res.result}
        s = scorer.UnitTests().summarize([ln])
        assert s["per_tag"]["rus"]["same_tests_as"] == ["Cyrl"]
    assert failed.result["per_tag"]["rus"]["ids"] == ok.result["per_tag"]["rus"]["ids"]


def test_twins_from_digests_equal_twins_from_explicit_id_sets():
    rng = random.Random(11)
    for _ in range(200):
        tags = ["a", "b", "c", "d"]
        xs, sets = [], {t: set() for t in tags}
        for p in range(rng.randint(1, 4)):
            for j in range(rng.randint(1, 4)):
                chosen = [t for t in tags if rng.random() < 0.6] or ["a"]
                xs.append(line(f"p{p}t{j}", document=f"d{p}", page=f"p{p}", tags=chosen))
                for t in chosen:
                    sets[t].add(f"p{p}t{j}")
        got = unit_tests.summarize(xs)["per_tag"]
        for t in got:
            want = sorted(u for u in got if u != t and sets[u] == sets[t])
            assert got[t].get("same_tests_as", []) == want, (t, sets)


def test_the_summarys_effective_documents_is_what_the_intervals_report():
    from omni_parse_bench import uncertainty
    pages = [score_line(f"d{i}", {"x": (n, 1, 1)}) for i, n in enumerate((1, 1, 2, 5, 9, 3))]
    s, got = scorer._summary(pages), uncertainty.intervals(pages, resamples=100)
    assert s["per_tag"]["x"]["effective_documents"] == got["per_tag"]["x"]["effective_documents"]
    assert s["families"]["text"]["effective_documents"] == got["families"]["text"]["effective_documents"]


def test_the_digest_does_not_depend_on_the_order_of_tests_or_pages_and_is_stable():
    ids = [f"test-{i}" for i in range(50)]
    assert scorer._ids(ids) == scorer._ids(reversed(ids)) == scorer._ids(sorted(ids))
    assert scorer._ids(["a"]) != scorer._ids(["b"]) and scorer._ids([]) == 0
    xs = [line(f"t{i}", document=f"d{i}", tags=["x", "y"]) for i in range(6)]
    a = unit_tests.summarize(xs)
    b = unit_tests.summarize(list(reversed(xs)))
    assert a == b and a["per_tag"]["x"]["same_tests_as"] == ["y"]
    # blake2b, not hash(): the same value in another interpreter with another hash seed
    code = ("from omni_parse_bench.scorers.unit_tests import unit_tests as u; print(u._ids(['a', 'b', 'c']))")
    outs = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True,
                           env={"PYTHONHASHSEED": str(seed), "PATH": ""}).stdout for seed in (1, 2)}
    assert outs == {f"{scorer._ids(['a', 'b', 'c'])}\n"}


def test_a_scored_page_carries_digests_that_summarize_reads_alike(tmp_path):
    from tests.test_scorer import PAGE, TESTS   # the scorer tests' own page
    sc = scorer.UnitTests().score({"html": "<p>alpha beta</p>"}, TESTS)
    ln = {"id": "p", "row": scorer.UnitTests().row_fields(PAGE), **sc.result}
    via_scores = scorer.UnitTests().summarize([ln])
    via_tests = unit_tests.summarize(unit_tests.lines(unit_tests.score({"html": "<p>alpha beta</p>"}, TESTS),
                                                      TESTS, PAGE))
    assert via_scores == via_tests


def test_the_format_family_is_reported_beside_the_headline_and_never_in_it():
    xs = [line("a", document="d1", test_type="present"), line("b", document="d2", test_type="table_cell"),
          line("c", document="d3", test_type="format", ok=False)]
    s = unit_tests.summarize(xs)
    assert set(s["families"]) == {"text", "tables", "format"}
    assert s["families"]["format"]["score"] == 0.0
    assert s["score"] == (s["families"]["text"]["score"] + s["families"]["tables"]["score"]) / 2
    only = unit_tests.summarize([xs[2]])
    assert only["score"] == 0.0     # a dataset with no headline family has the mean of the ones it has
