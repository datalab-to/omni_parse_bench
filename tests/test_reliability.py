"""Split-half reliability over synthetic score lines."""

import json
import random

import pytest

from omni_parse_bench import cli, uncertainty

N_SYSTEMS, N_DOCS, PER = 12, 300, 10


def page(document, base, x, *, tests_x=PER, suite="s"):
    """A score line for one document: PER base tests (tag "base") and `tests_x` tests of tag "x"; `base`
    and `x` are how many of each passed."""
    cb, cx = {"tests": PER, "passed": base}, {"tests": tests_x, "passed": x}
    total = {"tests": PER + tests_x, "passed": base + x}
    return {"id": f"{document}-p", "status": "scored", "row": {"document": document, "suite": suite},
            **total, "per_family": {"text": dict(total)}, "per_tag": {"base": cb, "x": cx},
            "per_test_type": {}, "per_arg_kind": {}, "per_derivation": {}}


def skill_of(i, n=N_SYSTEMS, low=0.3, high=0.8):
    return low + (high - low) * i / (n - 1)


def systems(px, *, seed=0, n_systems=N_SYSTEMS, n_docs=N_DOCS, low=0.3, high=0.8):
    """{name: lines}: system i passes a base test with its skill and an x test with `px(i, skill)`."""
    rng = random.Random(seed)
    out = {}
    for i in range(n_systems):
        skill = skill_of(i, n_systems, low, high)
        p = px(i, skill)
        out[f"sys{i}"] = [page(f"d{j}", sum(rng.random() < skill for _ in range(PER)),
                               sum(rng.random() < p for _ in range(PER))) for j in range(n_docs)]
    return out


EFFECT = (-0.12, 0.1, -0.05, 0.12, 0.0, -0.1, 0.06, -0.02, 0.11, -0.08, 0.04, 0.09)


def x_entry(runs, **kw):
    return uncertainty.reliability(runs, **kw)["per_tag"]["x"]


def test_a_slice_with_its_own_system_effect_ranks_beyond_the_other_tests_and_is_not_flagged():
    x = x_entry(systems(lambda i, s: s + EFFECT[i]))
    assert x["agreement"] > 0.9 and x["beyond_headline"] > 0.7 and not x["flag"] and "kind" not in x, x
    assert x["splits_used"] == {"agreement": 100, "beyond_headline": 100} and "reason" not in x
    assert (x["documents"], x["tests"]) == (N_DOCS, PER * N_DOCS)


def test_a_slice_of_pure_noise_is_flagged_noisy():
    x = x_entry(systems(lambda i, s: 0.5))
    assert x["agreement"] < 0.7 and x["beyond_headline"] < 0.7 and x["flag"] and x["kind"] == "noisy", x


@pytest.mark.parametrize("p", [0.02, 0.98])
def test_a_floor_or_ceiling_slice_is_flagged_noisy(p):
    x = x_entry(systems(lambda i, s: p))
    assert x["flag"] and x["kind"] == "noisy", x


def test_a_slice_every_system_fails_has_no_numbers_not_a_flag():
    x = x_entry(systems(lambda i, s: 0.0))
    assert x["agreement"] is None and x["flag"] is False and "kind" not in x
    assert "undefined in more than 20%" in x["reason"] and x["splits_used"]["agreement"] == 0


@pytest.mark.parametrize("slope", [0.5, 1.0, 1.5])
def test_a_slice_that_only_follows_skill_ranks_but_is_flagged_redundant(slope):
    x = x_entry(systems(lambda i, s: 0.55 + slope * (s - 0.55)))
    assert x["agreement"] > 0.9 and x["beyond_headline"] < 0.7, x
    assert x["flag"] and x["kind"] == "redundant", x


def test_a_slice_of_few_documents_has_no_numbers_and_is_not_flagged():
    got = x_entry(systems(lambda i, s: s, n_docs=8), min_documents=10)
    assert got["agreement"] is None and got["beyond_headline"] is None and got["flag"] is False
    assert "fewer than 10 effective documents" in got["reason"] and got["documents"] == 8


def test_fewer_than_five_systems_raises():
    four = dict(list(systems(lambda i, s: s).items())[:4])
    with pytest.raises(ValueError, match="at least 5 systems"):
        uncertainty.reliability(four)


def test_no_common_document_raises():
    runs = {k: [{**p, "row": {**p["row"], "document": f"{k}-{p['row']['document']}"}} for p in v]
            for k, v in systems(lambda i, s: s, n_docs=20).items()}
    with pytest.raises(ValueError, match="no document in common"):
        uncertainty.reliability(runs)


def test_documents_not_in_every_system_are_dropped_and_counted():
    runs = systems(lambda i, s: s, n_docs=40)
    runs["sys0"] = runs["sys0"][:30]
    runs["sys1"] = runs["sys1"][5:]
    runs["sys2"][10] = {**runs["sys2"][10], "tests": 21}     # d10 has another number of tests here
    got = uncertainty.reliability(runs, splits=20)
    assert got["documents_used"] == 24 and got["documents_dropped"] == 16 and got["systems"] == N_SYSTEMS


def test_the_same_seed_gives_the_same_result_and_another_other_splits():
    runs = systems(lambda i, s: s + EFFECT[i], n_docs=60)
    a = uncertainty.reliability(runs, splits=30, seed=1)
    assert a == uncertainty.reliability(runs, splits=30, seed=1)
    assert a != uncertainty.reliability(runs, splits=30, seed=2)
    assert a["reliability"]["splits"] == 30 and a["reliability"]["seed"] == 1


def test_the_order_of_documents_and_systems_does_not_matter():
    runs = systems(lambda i, s: s + EFFECT[i], n_docs=60)
    rng = random.Random(3)
    shuffled = {}
    for k in rng.sample(list(runs), len(runs)):
        shuffled[k] = rng.sample(runs[k], len(runs[k]))
    a, b = uncertainty.reliability(runs, splits=30), uncertainty.reliability(shuffled, splits=30)
    for kind in uncertainty.SLICES:
        for k, e in a[kind].items():
            assert e["agreement"] == pytest.approx(b[kind][k]["agreement"])
            assert e["beyond_headline"] == pytest.approx(b[kind][k]["beyond_headline"])


def test_adding_a_constant_to_every_systems_slice_leaves_the_result_unchanged():
    runs = systems(lambda i, s: s + EFFECT[i], n_docs=60)
    # Each x count becomes x + 10 of 20 tests: every system's rate is 0.5 * rate + 0.5, a shift and a scale.
    moved = {k: [page(p["row"]["document"], p["per_tag"]["base"]["passed"], p["per_tag"]["x"]["passed"] + 10,
                      tests_x=20) for p in v] for k, v in runs.items()}
    a, b = x_entry(runs), x_entry(moved)
    assert a["beyond_headline"] == pytest.approx(b["beyond_headline"])
    assert a["agreement"] == pytest.approx(b["agreement"])


def test_a_slice_equal_to_all_tests_says_there_are_no_tests_outside_it():
    got = uncertainty.reliability(systems(lambda i, s: s))
    fam = got["families"]["text"]
    assert fam["reason"] == "no tests outside the slice" and not fam["flag"]
    assert fam["beyond_headline"] is None


def test_an_odd_number_of_documents_gives_a_larger_second_half():
    runs = systems(lambda i, s: s + EFFECT[i], n_docs=61)
    got = uncertainty.reliability(runs, splits=20)
    assert got["documents_used"] == 61 and got["per_tag"]["x"]["splits_used"]["agreement"] == 20


def test_spearman_ties_and_the_brown_step():
    assert uncertainty._ranks([3, 1, 3, 2]) == [3.5, 1, 3.5, 2]
    assert uncertainty._spearman([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1)
    assert uncertainty._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == pytest.approx(-1)
    assert uncertainty._spearman([1, 1, 1], [1, 2, 3]) is None
    assert uncertainty._brown(0.5) == pytest.approx(2 / 3)
    assert uncertainty._brown(-1) == -1 and uncertainty._brown(-1.2) == -1
    assert uncertainty._brown(1) == 1 and uncertainty._brown(None) is None
    assert uncertainty._brown(-0.9999) == -1     # clipped: 2r / (1 + r) is below -1 here


def test_residuals_remove_the_fit_and_need_variance():
    r = uncertainty._residuals([1, 2, 3, 5], [1, 2, 3, 4])
    assert sum(r) == pytest.approx(0)
    assert uncertainty._residuals([1, 2, 3], [4, 4, 4]) is None
    assert uncertainty._residuals([2, 4, 6], [1, 2, 3]) == pytest.approx([0, 0, 0])


def test_five_systems_within_a_point_rank_by_noise():
    x = x_entry(systems(lambda i, s: s, n_systems=5, low=0.50, high=0.51, n_docs=200))
    assert x["agreement"] < 0.7 and x["flag"] and x["kind"] == "noisy", x


def test_a_test_with_several_tags_counts_under_each_and_stays_in_the_other_tests_of_the_others():
    """20 systems, 400 documents of 12 tests, each carrying 2 of 12 tags: tag "sig" has its own system
    effect, every other tag follows skill alone."""
    rng = random.Random(5)
    n_sys, n_docs, per = 20, 400, 12
    gold = [[rng.sample([f"t{k}" for k in range(12)], 2) for _ in range(per)] for _ in range(n_docs)]
    effect = [rng.uniform(-0.15, 0.15) for _ in range(n_sys)]
    runs = {}
    for s in range(n_sys):
        skill = 0.3 + 0.5 * s / (n_sys - 1)
        lines = []
        for j, tests in enumerate(gold):
            tags: dict[str, dict[str, int]] = {}
            passed = 0
            for tags_of in tests:
                ok = rng.random() < skill + (effect[s] if "t0" in tags_of else 0)
                passed += ok
                for t in tags_of:
                    c = tags.setdefault(t, {"tests": 0, "passed": 0})
                    c["tests"] += 1
                    c["passed"] += ok
            lines.append({"id": f"d{j}", "row": {"document": f"d{j}", "suite": f"s{j % 4}"}, "tests": per,
                          "passed": passed, "per_family": {"text": {"tests": per, "passed": passed}},
                          "per_tag": tags, "per_test_type": {}, "per_arg_kind": {}, "per_derivation": {}})
        runs[f"s{s}"] = lines
    got = uncertainty.reliability(runs, splits=60)
    tags = got["per_tag"]
    assert len(tags) == 12 and sum(e["tests"] for e in tags.values()) == 2 * per * n_docs
    assert tags["t0"]["flag"] is False and tags["t0"]["beyond_headline"] > 0.7, tags["t0"]
    assert [k for k, e in tags.items() if e["flag"]] == [k for k in tags if k != "t0"]
    assert all(e["kind"] == "redundant" for k, e in tags.items() if k != "t0")
    assert len(tags) == 12
    assert got["slices_with_numbers"] == 16 and len(got["per_suite"]) == 4
    assert got["slices_without_numbers"] == 1     # the family covers every test


@pytest.mark.parametrize("kw", [{"splits": 5}, {"splits": True}, {"splits": 50.0}, {"min_documents": 1}])
def test_bad_options_raise(kw):
    with pytest.raises(ValueError):
        uncertainty.reliability(systems(lambda i, s: s, n_docs=12), **kw)


def graded(folder, pages):
    (folder / "unit_tests").mkdir(parents=True)
    (folder / "unit_tests" / "scores.jsonl").write_text("\n".join(map(json.dumps, pages)) + "\n")
    return str(folder)


def test_the_command_prints_json_and_can_show_only_the_flagged(tmp_path, capsys):
    runs = systems(lambda i, s: s, n_systems=5, n_docs=60)
    folders = [graded(tmp_path / f"run{i}", lines) for i, lines in enumerate(runs.values())]
    assert cli.main(["reliability", *folders, "--splits", "20", "--min-documents", "10"]) == 0
    got = json.loads(capsys.readouterr().out)
    assert got["systems"] == 5 and got["reliability"]["splits"] == 20 and "x" in got["per_tag"]
    assert cli.main(["reliability", *folders, "--splits", "20", "--flagged"]) == 0
    only = json.loads(capsys.readouterr().out)
    assert all(e["flag"] for kind in uncertainty.SLICES for e in only[kind].values())
    assert only["per_tag"]["x"]["kind"] == "redundant"
    assert only["documents_used"] == 60
    assert only["slices_with_numbers"] == got["slices_with_numbers"]
    assert only["slices_without_numbers"] == got["slices_without_numbers"]
    with pytest.raises(ValueError, match="at least 5"):
        cli.main(["reliability", *folders[:4]])


def test_the_command_checks_its_options_and_the_run_names(tmp_path):
    runs = systems(lambda i, s: s, n_systems=5, n_docs=20)
    folders = [graded(tmp_path / f"run{i}", lines) for i, lines in enumerate(runs.values())]
    for flag, value in (("--threshold", "1.5"), ("--threshold", "nan"), ("--threshold", "-1"),
                        ("--seed", "-1")):
        with pytest.raises(ValueError, match=flag):
            cli.main(["reliability", *folders, flag, value])
    twin = graded(tmp_path / "other" / "run0", runs["sys0"])
    with pytest.raises(ValueError, match="folder's name"):
        cli.main(["reliability", *folders[:4], twin])


def sized(sizes, px, *, seed=0, n_systems=N_SYSTEMS):
    """{name: lines} with `sizes[j]` x tests in document j, the same for every system; system i passes
    an x test with `px(i, skill)` and a base test with its skill."""
    rng = random.Random(seed)
    out = {}
    for i in range(n_systems):
        skill = skill_of(i, n_systems)
        p = px(i, skill)
        out[f"sys{i}"] = [page(f"d{j}", sum(rng.random() < skill for _ in range(PER)),
                               sum(rng.random() < p for _ in range(m)), tests_x=m)
                          for j, m in enumerate(sizes)]
    return out


def test_effective_documents_is_the_count_for_equal_documents_and_less_for_skewed_ones():
    assert uncertainty._effective([4, 4, 4, 4, 4]) == 5
    assert uncertainty._effective([3, 1]) == pytest.approx(1.6)     # 16 / 10
    assert uncertainty._effective([9, 1, 1, 1]) == pytest.approx(144 / 84)
    assert uncertainty._effective([]) == 0
    got = uncertainty.intervals([page(f"d{j}", 5, 5) for j in range(10)], resamples=100)
    assert got["per_tag"]["x"]["effective_documents"] == 10 == got["per_tag"]["x"]["documents"]
    assert got["headline"]["effective_documents"] == 10


def test_intervals_and_paired_report_effective_documents():
    a = [page(f"d{j}", 5, 5, tests_x=1 if j else 40) for j in range(20)]
    b = [page(f"d{j}", 4, 4, tests_x=1 if j else 40) for j in range(20)]
    x = uncertainty.intervals(a, resamples=100)["per_tag"]["x"]
    assert x["documents"] == 20 and x["effective_documents"] == pytest.approx(59 ** 2 / (1600 + 19), abs=0.05)
    p = uncertainty.paired(a, b, resamples=100)
    assert p["per_tag"]["x"]["documents"] == 20
    assert p["per_tag"]["x"]["effective_documents"] == x["effective_documents"]
    assert p["headline"]["effective_documents"] < 20


def test_the_minimum_counts_effective_documents():
    sizes = [100] + [1] * 9                  # 10 documents, but one holds nearly all the tests
    got = x_entry(sized(sizes, lambda i, s: s), min_documents=10)
    assert got["documents"] == 10 and got["effective_documents"] < 2
    assert got["agreement"] is None and "effective documents" in got["reason"]


def totals(flags, sizes):
    a = sum(s for f, s in zip(flags, sizes, strict=True) if f)
    return a, sum(sizes) - a


def test_balanced_halves_hold_nearly_equal_numbers_of_tests_and_random_halves_do_not():
    rng = random.Random(1)
    sizes = [max(1, int(3 * rng.paretovariate(1.5))) for _ in range(300)]

    def gap(balanced):     # the mean share of all tests by which the halves differ
        halves = uncertainty._halves(sizes, 100, random.Random(2), balanced)
        return sum(abs(a - b) for a, b in (totals(f, sizes) for f in halves)) / 100 / sum(sizes)

    assert gap(True) < 0.01 and gap(False) > 4 * gap(True)
    odd = [*sizes, 40]      # the odd one out goes to a random half
    assert {sum(f) for f in uncertainty._halves(odd, 20, random.Random(2), True)} == {150, 151}
    for flags in uncertainty._halves(sizes, 5, random.Random(3), True):
        assert sum(flags) == 150                                # also equal in documents
    even = uncertainty._halves([1, 2, 3, 4], 5, random.Random(0), True)
    assert all(sum(f) == 2 for f in even)


def test_balanced_halves_give_a_skewed_fixture_a_higher_agreement():
    """Systems rank one way on the few large documents (most of the tests) and the other way on the many
    small ones, so a random half that holds more large documents ranks them differently from the other:
    halves balanced by test count hold the same mix."""
    rng = random.Random(6)
    sizes = [30] * 20 + [3] * 100
    runs = {}
    for i in range(N_SYSTEMS):
        skill = skill_of(i)
        lines = []
        for j, m in enumerate(sizes):
            p = 0.5 + (EFFECT[i] if m < 10 else -EFFECT[i])
            lines.append(page(f"d{j}", sum(rng.random() < skill for _ in range(PER)),
                              sum(rng.random() < p for _ in range(m)), tests_x=m))
        runs[f"sys{i}"] = lines
    on = x_entry(runs, balanced=True, min_documents=5)["agreement"]
    off = x_entry(runs, balanced=False, min_documents=5)["agreement"]
    assert on > off + 0.05, (on, off)     # 0.73 against 0.63 here; over 8 seeds, balanced won every time


def test_the_balanced_option_is_recorded_and_cli_turns_it_off(tmp_path, capsys):
    runs = systems(lambda i, s: s, n_systems=5, n_docs=40)
    folders = [graded(tmp_path / f"run{i}", lines) for i, lines in enumerate(runs.values())]
    assert uncertainty.reliability(runs, splits=20)["reliability"]["balanced"] is True
    assert uncertainty.reliability(runs, splits=20, balanced=False)["reliability"]["balanced"] is False
    assert cli.main(["reliability", *folders, "--splits", "20", "--random-halves"]) == 0
    assert json.loads(capsys.readouterr().out)["reliability"]["balanced"] is False
