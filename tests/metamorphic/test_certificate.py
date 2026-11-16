"""CERTIFICATE.md is current, and every status it shows is what the tests really do."""
from __future__ import annotations

import inspect
import os
import re
import sys

import pytest

from metamorphic.common import CELL, CHECKS, DEVIATION_STATUS, DEVIATIONS, HOLDS, LAYOUT, LIVE, NUMBER, ORDER
from metamorphic.common import (DATASET_REVISION, MANIFEST_SHA256, POOLS, REAL, RELATIONS, REPEAT, RUN_IN_CI,
                               TEXT, manifest_sha256, text_strings)
from metamorphic.render_certificate import (COMMAND, HERE, MODULES, ROOT, compare, examples_drawn,
                                           load_every_test_file, render)


def test_the_certificate_is_current():
    assert (HERE / "CERTIFICATE.md").read_text() == render(), f"CERTIFICATE.md is stale: run {COMMAND}"


def test_each_status_matches_the_tests_xfail_marker():
    load_every_test_file()
    for label, r in RELATIONS.items():
        xfails = [m for m in getattr(r["fn"], "pytestmark", []) if m.name == "xfail"]
        if r["status"] == HOLDS:
            assert not xfails and label not in DEVIATIONS, f"{label} is HOLDS, but its test expects a failure"
        else:
            assert label in DEVIATIONS, f"{label} is {r['status']}, but known_deviations.json has no entry"
            assert len(xfails) == 1, f"{label} is {r['status']}, but its test is not @deviation({label!r})"
            kw = xfails[0].kwargs
            assert kw["strict"] and kw["raises"] is AssertionError, label
            assert kw["reason"].endswith(f"See known_deviations.json, {label}."), label
            assert DEVIATIONS[label]["status"] == DEVIATION_STATUS[r["status"]], f"{label}: status differs"
    assert set(DEVIATIONS) <= set(RELATIONS), "known_deviations.json has an entry no relation states"
    fields = {"status", "description", "counterexample", "why_this_status", "effect_on_scores",
              "effect_basis", "how_common", "who_is_affected", "enumerated_over_real_tests"}
    for label, e in DEVIATIONS.items():
        assert fields <= set(e) and e["effect_on_scores"] in ("none seen", "small", "unknown"), label
        assert e["enumerated_over_real_tests"] == ("real_ids" in e), label
    for c in CHECKS:
        if c["role"] != "relation":
            assert not any(m.name == "xfail" for m in getattr(c["fn"], "pytestmark", [])), c["fn"].__name__


def test_every_test_is_registered_and_says_why_it_matters():
    load_every_test_file()
    registered = {c["fn"].__name__ for c in CHECKS}
    for name in MODULES:
        for fname, _ in inspect.getmembers(sys.modules[f"metamorphic.{name}"], inspect.isfunction):
            if fname.startswith("test_"):
                assert fname in registered, f"{name}.{fname} is not registered (@relation etc.)"
    for c in CHECKS:
        assert set(c["labels"]) <= set(RELATIONS), f"{c['fn'].__name__} names a label no relation states"
    real_checks = {c["fn"].__name__ for c in CHECKS if c["role"] == "real"}
    assert all(e["found_by"] in real_checks for e in DEVIATIONS.values() if "found_by" in e)


@pytest.mark.skipif(LIVE or os.environ.get("HYPOTHESIS_PROFILE", "ci") != "ci",
                    reason="RUN_IN_CI counts the CI profile's examples on the fixtures")
def test_the_certificate_counts_the_examples_it_says_ran_in_ci():
    """Each test listed in RUN_IN_CI draws exactly that many examples per item in CI."""
    load_every_test_file()
    fns = {c["fn"].__name__: c["fn"] for c in CHECKS}
    got = {name: examples_drawn(fns[name]) for name in RUN_IN_CI}
    want = {name: [n] * len(got[name]) for name, n in RUN_IN_CI.items()}
    assert got == want, "update RUN_IN_CI in common.py"


def test_every_deviation_cites_files_that_exist():
    """Each path a deviation's 'why' cites exists in this repository, and each docs case id it cites is in
    docs/scoring; an intended one cites at least one."""
    docs = "".join(p.read_text() for p in (ROOT / "docs" / "scoring").glob("*.md"))
    for label, e in DEVIATIONS.items():
        why = e["why_this_status"]
        paths = re.findall(r"(?:docs|omni_parse_bench)/[\w/.-]+\.(?:md|py)", why)
        assert all((ROOT / p).exists() for p in paths), (label, paths)
        if e["status"] == "intended and documented":
            assert paths, f"{label}: an intended deviation cites the doc or code that says so"
        for ids in re.findall(r"cases? ((?:[a-z]+(?:-[a-z]+)+(?:, )?)+)", why):
            assert all(f"`{case}`" in docs for case in ids.split(", ")), (label, ids)


def test_what_a_deviation_quotes_is_in_the_files_it_cites():
    """A phrase a deviation's 'why' quotes (in single quotes, 12 characters or more; '...' stands for words
    left out) and a name it puts in backticks (an identifier, or a call written `name()`) is in one of the
    files it cites, so a justification does not outlive the code or doc it names."""
    missing = []
    for label, e in DEVIATIONS.items():
        why = e["why_this_status"]
        paths = re.findall(r"(?:docs|omni_parse_bench)/[\w/.-]+\.(?:md|py)", why)
        # a comment that runs over several lines is read as one: the `#` that starts each line is dropped
        read = [re.sub(r"\n\s*#", " ", (ROOT / p).read_text()) for p in paths]
        text = " ".join(" ".join(r.split()) for r in read).lower()
        quoted = re.findall(r"(?<!\w)'([^']{12,}?)'(?!\w)", why)
        ident = r"[A-Za-z_][\w.]{2,}(?:\(\))?"
        names = [n for n in re.findall(r"`([^`]+)`", why) if re.fullmatch(ident, n)]
        for q in quoted:
            parts = [" ".join(x.split()).lower() for x in re.split(r"\.\.\.|…", q) if x.strip()]
            missing += [(label, "quotes", x) for x in parts if x not in text]
        missing += [(label, "names", n) for n in names if n.lower() not in text]
    assert not missing, missing


@pytest.mark.skipif(not LIVE, reason="needs the dataset: set OPB_DATASET to its root")
def test_the_certificate_counts_the_real_tests_it_says():
    assert manifest_sha256(os.environ["OPB_DATASET"]) == MANIFEST_SHA256, \
        f"OPB_DATASET is not revision {DATASET_REVISION[:7]} of the dataset: its manifest differs"
    from metamorphic.test_fold_and_case import EXACT, TESTS
    from metamorphic.test_text_matching import DIGIT_EDGED
    sizes = {"number": len(NUMBER), "order": len(ORDER), "exact text": len(EXACT),
             "digit-edged text": len(DIGIT_EDGED["present"]),
             "digit-edged repeat": len(DIGIT_EDGED["repeat"]),
             "digit-edged order": len(DIGIT_EDGED["order"]),
             "text strings": sum(len(text_strings(t.params)) for t in TESTS),
             "text tests": len([*TEXT, *ORDER, *REPEAT, *CELL])}
    assert sizes == {k: n for k, (_, n) in REAL.items()}, "update REAL in common.py, then " + COMMAND


def test_the_certificate_pools_are_the_loaded_tests():
    """The pool sizes the certificate prints are those loaded: the fixtures in CI, the dataset when set."""
    from metamorphic.test_fold_and_case import EXACT
    from metamorphic.test_text_matching import DIGIT_EDGED
    sizes = {"text, order, table_cell": len(TEXT + ORDER + CELL), "repeat": len(REPEAT),
             "text, number": len(TEXT + NUMBER), "layout": len(LAYOUT), "number": len(NUMBER),
             "digit-edged text, repeat": len(DIGIT_EDGED["present"]) + len(DIGIT_EDGED["repeat"]),
             "exact text": len(EXACT), "text, order, repeat, table_cell": len(TEXT + ORDER + REPEAT + CELL),
             "batch": len(TEXT + NUMBER + ORDER + REPEAT + CELL)}
    assert sizes == {k: v[2 if LIVE else 1] for k, v in POOLS.items()}, "update POOLS in common.py"


def test_the_run_report_flags_a_mismatch(tmp_path):
    """`render_certificate.py --run` agrees with a run where every test does what its status says, and flags a
    HOLDS test that failed and a DEVIATES test that passed."""
    load_every_test_file()

    def report(outcome) -> str:
        cases = "".join(f'<testcase classname="x" name="{c["fn"].__name__}">{outcome(c)}</testcase>'
                        for c in CHECKS)
        (tmp_path / "junit.xml").write_text(f"<testsuites><testsuite>{cases}</testsuite></testsuites>")
        return compare(tmp_path / "junit.xml")[1]

    def as_certified(c):
        xfail = c["role"] == "relation" and RELATIONS[c["labels"][0]]["status"] != HOLDS
        return '<skipped type="pytest.xfail" message="x"/>' if xfail else ""

    assert report(as_certified)
    assert not report(lambda c: "<failure/>" if c["fn"] is RELATIONS["M2a"]["fn"] else as_certified(c))
    assert not report(lambda c: "" if c["fn"] is RELATIONS["M16"]["fn"] else as_certified(c))
