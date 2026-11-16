"""Split-half reliability over synthetic score lines."""

import json
import random
import time

import pytest

from omni_parse_bench import cli, uncertainty

N_SYSTEMS, N_DOCS, PER = 12, 300, 10


def page(document, base, x, *, suite="s"):
    """A score line for one document with PER base tests (tag "base") and PER tests of tag "x"; `base` and
    `x` are how many of each passed."""
    cb, cx = {"tests": PER, "passed": base}, {"tests": PER, "passed": x}
    return {"id": f"{document}-p", "status": "scored", "row": {"document": document, "suite": suite},
            "tests": 2 * PER, "passed": base + x,
            "per_family": {"text": {"tests": 2 * PER, "passed": base + x}},
            "per_tag": {"base": cb, "x": cx}, "per_test_type": {}, "per_arg_kind": {}, "per_derivation": {}}


def systems(effect, *, seed=0, n_systems=N_SYSTEMS, n_docs=N_DOCS):
    """{name: lines}: system i has skill from 0.3 up to 0.8 on every test; its "x" tests also move by
    `effect(i)`, a system-specific effect."""
    rng = random.Random(seed)
    out = {}
    for i in range(n_systems):
        skill = 0.3 + 0.5 * i / (n_systems - 1)
        px = min(1, max(0, skill + effect(i)))
        out[f"sys{i}"] = [page(f"d{j}", sum(rng.random() < skill for _ in range(PER)),
                               sum(rng.random() < px for _ in range(PER))) for j in range(n_docs)]
    return out


def own_effect(i):
    return (-0.12, 0.1, -0.05, 0.12, 0.0, -0.1, 0.06, -0.02, 0.11, -0.08, 0.04, 0.09)[i]


def test_a_slice_with_its_own_system_effect_is_reliable_beyond_the_headline():
    got = uncertainty.reliability(systems(own_effect), splits=100)
    x = got["per_tag"]["x"]
    assert x["agreement"] > 0.9 and x["beyond_headline"] > 0.7 and not x["flag"], x
    assert x["splits_used"] == 100 and "reason" not in x and x["documents"] == N_DOCS
    assert x["tests"] == PER * N_DOCS


def test_a_slice_that_is_only_skill_ranks_but_adds_nothing_and_is_flagged():
    got = uncertainty.reliability(systems(lambda i: 0.0), splits=100)
    x = got["per_tag"]["x"]
    assert x["agreement"] > 0.8 and x["beyond_headline"] < 0.7 and x["flag"], x


def test_a_slice_of_few_documents_has_no_numbers_and_is_not_flagged():
    runs = systems(own_effect, n_docs=8)
    got = uncertainty.reliability(runs, min_documents=10)["per_tag"]["x"]
    assert got["agreement"] is None and got["beyond_headline"] is None and got["flag"] is False
    assert "fewer than 10 documents" in got["reason"] and got["documents"] == 8


def test_fewer_than_three_systems_raises():
    two = dict(list(systems(own_effect).items())[:2])
    with pytest.raises(ValueError, match="at least 3 systems"):
        uncertainty.reliability(two)


def test_no_common_document_raises():
    runs = systems(own_effect, n_docs=20)
    runs = {k: [{**p, "row": {**p["row"], "document": f"{k}-{p['row']['document']}"}} for p in v]
            for k, v in runs.items()}
    with pytest.raises(ValueError, match="no document in common"):
        uncertainty.reliability(runs)


def test_documents_not_in_every_system_are_dropped_and_counted():
    runs = systems(own_effect, n_docs=40)
    runs["sys0"] = runs["sys0"][:30]
    runs["sys1"] = runs["sys1"][5:]
    mismatched = runs["sys2"]
    mismatched[10] = {**mismatched[10], "tests": 21}
    got = uncertainty.reliability(runs, splits=20)
    assert got["documents_used"] == 24 and got["documents_dropped"] == 16 and got["systems"] == N_SYSTEMS


def test_the_same_seed_gives_the_same_result_and_another_gives_other_splits():
    runs = systems(own_effect, n_docs=60)
    a = uncertainty.reliability(runs, splits=30, seed=1)
    assert a == uncertainty.reliability(runs, splits=30, seed=1)
    assert a != uncertainty.reliability(runs, splits=30, seed=2)
    assert a["reliability"] == {"method": "split-half over documents, Spearman-Brown corrected, median over "
                                "splits", "splits": 30, "seed": 1, "threshold": 0.7, "min_documents": 10}


def test_a_slice_with_no_variance_between_systems_is_left_without_numbers():
    runs = {f"s{i}": [page(f"d{j}", PER, PER) for j in range(40)] for i in range(4)}
    got = uncertainty.reliability(runs, splits=20)["per_tag"]["x"]
    assert got["agreement"] is None and got["flag"] is False and got["splits_used"] == 0
    assert "undefined" in got["reason"]


def test_ties_take_the_average_rank_and_the_spearman_is_the_textbook_one():
    assert uncertainty._ranks([3, 1, 3, 2]) == [3.5, 1, 3.5, 2]
    assert uncertainty._spearman([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1)
    assert uncertainty._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1)
    assert uncertainty._spearman([1, 1, 1], [1, 2, 3]) is None
    assert uncertainty._brown(0.5) == pytest.approx(2 / 3)


@pytest.mark.parametrize("kw", [{"splits": 5}, {"splits": True}, {"splits": 50.0}, {"min_documents": 1}])
def test_bad_options_raise(kw):
    with pytest.raises(ValueError):
        uncertainty.reliability(systems(own_effect, n_docs=12), **kw)


def graded(folder, pages):
    (folder / "unit_tests").mkdir(parents=True)
    (folder / "unit_tests" / "scores.jsonl").write_text("\n".join(map(json.dumps, pages)) + "\n")
    return str(folder)


def test_the_command_prints_json_and_can_show_only_the_flagged(tmp_path, capsys):
    runs = systems(lambda i: 0.0, n_systems=4, n_docs=60)
    folders = [graded(tmp_path / f"run{i}", lines) for i, lines in enumerate(runs.values())]
    assert cli.main(["reliability", *folders, "--splits", "20", "--min-documents", "10"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["systems"] == 4 and got["reliability"]["splits"] == 20 and "x" in got["per_tag"]
    assert cli.main(["reliability", *folders, "--splits", "20", "--threshold", "1.01", "--flagged"]) == 0
    only = json.loads(capsys.readouterr().out)
    assert all(e["flag"] for kind in uncertainty.SLICES for e in only[kind].values())
    assert only["per_tag"] and only["documents_used"] == 60
    with pytest.raises(ValueError, match="at least 3"):
        cli.main(["reliability", *folders[:2]])


def test_full_size_data_takes_well_under_a_minute():
    rng = random.Random(0)
    n_sys, n_docs = 38, 1800
    skill = [rng.random() for _ in range(n_sys)]
    doc_tags = [[f"t{k}" for k in rng.sample(range(100), 20)] for _ in range(n_docs)]  # one gold
    runs = {}
    for s in range(n_sys):
        pages = []
        for j in range(n_docs):
            fam = {"text": {"tests": 20, "passed": 0}}
            tags = {t: {"tests": 1, "passed": 0} for t in doc_tags[j]}
            p = 0
            for c in (*fam.values(), *tags.values()):
                c["passed"] = sum(rng.random() < skill[s] for _ in range(c["tests"]))
            p = fam["text"]["passed"]
            pages.append({"id": f"d{j}", "row": {"document": f"d{j}", "suite": f"s{j % 8}"}, "tests": 20,
                          "passed": p, "per_family": fam, "per_tag": tags, "per_test_type": {},
                          "per_arg_kind": {}, "per_derivation": {}})
        runs[f"s{s}"] = pages
    start = time.perf_counter()
    got = uncertainty.reliability(runs, splits=100)
    took = time.perf_counter() - start
    assert took < 60
    assert len(got["per_tag"]) == 100 and all(e["splits_used"] > 0 for e in got["per_tag"].values())
    assert got["documents_used"] == n_docs
