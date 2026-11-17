"""The registry behind CERTIFICATE.md, the tests the relations run on, and the helpers several files use."""
from __future__ import annotations

import hashlib
import html
import inspect
import json
import os
import re
import types
from pathlib import Path

import pytest
from test_invariants import answer
from test_properties import LIVE, TESTS

from omni_parse_bench import data, views
from omni_parse_bench.scorers.unit_tests import runners

if os.environ.get("OPB_DATASET") and not LIVE:
    raise RuntimeError(f"OPB_DATASET={os.environ['OPB_DATASET']!r} holds no dataset (no manifest)")

# ------------------------------------------------------------------------------------------- registry

HOLDS = "HOLDS"
INTENDED = "DEVIATES (intended, documented)"
LIMITATION = "DEVIATES (known limitation)"
BUG = "DEVIATES (bug)"
# The same statuses as known_deviations.json writes them.
DEVIATION_STATUS = {INTENDED: "intended and documented", LIMITATION: "known limitation", BUG: "bug"}

DEVIATIONS = json.loads((Path(__file__).parent / "known_deviations.json").read_text())

RELATIONS: dict[str, dict] = {}     # label -> its promise, its status and the test that states it
CHECKS: list[dict] = []             # every registered test function, in the order the files define them


def _register(fn, role: str, status: str | None = None, over: str | None = None, note: str | None = None,
              pool: str | None = None, case_of: dict[str, dict] | None = None):
    """Reads the docstring: '<promise> [<labels>]', then a line 'Why it matters for a score: ...'."""
    first, why, _ = inspect.cleandoc(fn.__doc__).partition("\nWhy it matters for a score: ")
    found = re.fullmatch(r"(.*\S) \[(M\d+[a-z]?(?:, M\d+[a-z]?)*)\]", " ".join(first.split()))
    assert found and why, f"{fn.__name__}: the docstring opens '<promise> [M1a]', then 'Why it matters ...'"
    promise, labels = found[1], found[2].split(", ")
    CHECKS.append({"fn": fn, "role": role, "labels": labels, "over": over, "note": note, "pool": pool,
                   "case_of": case_of or {}})
    if role == "relation":
        assert len(labels) == 1 and labels[0] not in RELATIONS, f"{fn.__name__}: one new label per relation"
        RELATIONS[labels[0]] = {"promise": promise, "status": status, "fn": fn}
    return fn


def relation(status: str, domain: str | None = None, pool: str | None = None):
    """Registers the test that states a relation: its docstring opens with the promise and its label.
    `domain` describes its input space in words ('12 combinations: ...'); `pool` (a key of POOLS) names the
    loaded tests its examples are drawn from. Both are shown in the certificate."""
    return lambda fn: _register(fn, "relation", status=status, note=domain, pool=pool)


def more_evidence(pool: str | None = None, case_of: dict[str, dict] | None = None):
    """Registers a further test of the relations its docstring labels (fixed cases, or the loaded tests).
    `case_of` maps a label to the parametrize values of the items that test it, when not every item does
    ({"M13a": {"kind": "present"}}); the certificate counts only those items for that label."""
    return lambda fn: _register(fn, "more", pool=pool, case_of=case_of)


def every_real_test(over: str | dict[str, str], note: str | None = None):
    """Registers a check over every real test in `over` (a key of REAL, or one per label); it needs the
    dataset. `note` is shown in the certificate beside the count."""
    skip = pytest.mark.skipif(not LIVE, reason="needs the dataset: set OPB_DATASET to its root")
    return lambda fn: _register(skip(fn), "real", over=over, note=note)


def deviation(label: str):
    """The strict xfail of a relation the scorer does not keep: it must fail, by an assertion."""
    return pytest.mark.xfail(strict=True, raises=AssertionError,
                             reason=f"{DEVIATIONS[label]['description']} See known_deviations.json, {label}.")


def known_ids(label: str) -> set[str]:
    """The real ids listed as deviating for one relation in known_deviations.json (none when it holds)."""
    return set(DEVIATIONS.get(label, {}).get("real_ids", []))

# ---------------------------------------------------------------------------------------- the tests

def is_exact(p) -> bool:
    """Whether a test's params ask for `exact_case` (only a `present` text arg can)."""
    return isinstance(p, runners.Present) and isinstance(p.content, runners.Text) and p.content.exact_case


def of(*kinds):
    # Note: the relations that say case does not matter (M2a, M2e, M3, M7, M13a, M14, M15a/b, ...) draw their
    # tests here, and a test that sets `exact_case` is left out of every one of them (`exact_case_tests`
    # holds them): `passes` refuses such a test too, so that case-insensitivity cannot be weakened by one.
    return [t for t in TESTS if isinstance(t.params, kinds) and not is_exact(t.params)]


def exact_case_tests():
    """The loaded tests whose text arg sets `exact_case` (the fixtures hold two; M29 runs them)."""
    return [t for t in TESTS if is_exact(t.params)]


TEXT = [t for t in of(runners.Present) if isinstance(t.params.content, runners.Text)]
NUMBER = [t for t in of(runners.Present) if isinstance(t.params.content, runners.Number)]
ORDER = of(runners.Order)
REPEAT = [t for t in of(runners.Repeat) if isinstance(t.params.content, runners.Text)]
REPEAT_NUMBER = [t for t in of(runners.Repeat) if isinstance(t.params.content, runners.Number)]
CELL, LAYOUT = of(runners.TableCell), of(runners.LayoutKind)
for _name, _tests in [("text", TEXT), ("number", NUMBER), ("order", ORDER), ("repeat", REPEAT),
                      ("table_cell", CELL), ("layout_kind", LAYOUT)]:
    assert _tests, f"no {_name} tests: check tests/fixtures/invariants/ or OPB_DATASET"


def text_strings(p) -> list[str]:
    """The text strings a test compares, in the order an id's `#n` counts them from 0: a present test's text;
    an order test's `before`, `after`; a repeat test's text; a table_cell test's cell, headings, section, row
    groups and relations. A number, latex or layout_kind test has none."""
    if isinstance(p, runners.Present):
        return [p.content.text] if isinstance(p.content, runners.Text) else []
    if isinstance(p, runners.Order):
        return [p.before, p.after]
    if isinstance(p, runners.Repeat):
        return [p.content.text] if isinstance(p.content, runners.Text) else []
    if isinstance(p, runners.TableCell):
        section = [p.section] if p.section else []
        return [p.cell, *p.headings, *section, *p.row_groups, *p.relations.values()]
    return []


# Each population a check over every real test runs over, and its size in the published dataset.
DATASET_REVISION = "d70182b9f901d1660a27e60bf6be6d6e6ea83013"
# The sha256 of that revision's manifest.parquet (the Hugging Face file's LFS sha256). `--run` and
# test_certificate.py check it when OPB_DATASET is set. It pins the list of pages, not the gold files.
MANIFEST_SHA256 = "5cc5611ad6e1d32e0e39c91ce23da913e63ba775e414a7734c7d9c1768139c6b"
# test_certificate.py checks these sizes against the dataset when OPB_DATASET is set.
# The loaded tests examples are drawn from: how many the fixtures hold (CI) and the dataset (checked by
# test_certificate.py, the fixtures always and the dataset when OPB_DATASET is set).
POOLS = {
    "text, order, table_cell": ("text, order and table_cell tests", 8, 10_259),
    "repeat": ("repeat tests with text", 1, 35),
    "repeat number": ("repeat tests with a number", 6, 0),
    "text, number": ("text and number tests", 5, 4_007),
    "layout": ("layout_kind tests", 3, 2_403),
    "number": ("number tests", 2, 323),
    "digit-edged text, repeat": ("text and repeat tests with a digit at an end", 2, 431),
    "exact text": ("text tests with max_diffs 0", 2, 2_314),
    "text, order, repeat, table_cell": ("text, order, repeat and table_cell tests", 9, 10_294),
    "batch": ("text, number, order, repeat and table_cell tests", 17, 10_617),
}

# The Hypothesis tests whose input space runs out in CI before the profile's max_examples, and how many
# examples each draws there (per parametrized case; @example cases not counted). The certificate prints these
# counts; test_certificate.py counts them again.
RUN_IN_CI = {
    "test_a_footnote_mark_after_the_answer_does_not_change_a_present_verdict": 5,
    "test_a_span_starting_in_an_images_alt_text_is_read_the_same": 12,
    "test_an_equation_in_an_equivalent_form_passes_its_test": 8,
    "test_changing_one_digit_of_a_number_fails_its_test": 72,
    "test_a_digit_glued_to_a_number_fails_its_test": 40,
    "test_deleting_a_character_of_an_exact_text_fails_its_test": 2,
    "test_a_page_in_another_case_passes_every_text_test": 18,
    "test_a_digit_glued_to_a_loaded_digit_edged_test_fails_it": 10,
}

REAL = {
    "number": ("real number tests", 323),
    "order": ("real order tests", 1_189),
    "exact text": ("real text tests with max_diffs 0", 2_314),
    "digit-edged text": ("real text tests with an ASCII string starting or ending with a digit", 427),
    "digit-edged repeat": ("real repeat tests with an ASCII string starting or ending with a digit", 4),
    "digit-edged order": ("real order tests with an ASCII string starting or ending with a digit", 197),
    "text strings": ("text strings of the real text, order, repeat and table_cell tests", 24_682),
    "text tests": ("real text, order, repeat and table_cell tests", 10_294),
}

# --------------------------------------------------------------------------------------------- helpers

def manifest_sha256(dataset: str | Path) -> str:
    """The sha256 of a dataset folder's manifest file."""
    return hashlib.sha256((Path(dataset) / data.MANIFEST).read_bytes()).hexdigest()


def escaped(s: str) -> str:
    return html.escape(s, quote=False)


def passes(params, page: str, *, exact: bool = False) -> bool:
    """Whether the HTML `page` passes a test with these params. `exact` says the params set `exact_case`: a
    relation about the folded comparison (the default) refuses params that set it, and one about
    `exact_case` refuses params that do not, so neither can run on the other's tests."""
    assert is_exact(params) == exact, f"exact_case is {is_exact(params)}, the relation expects {exact}"
    kind = next(k for k, (cls, _) in runners.TYPES.items() if isinstance(params, cls))
    return runners.TYPES[kind][1](params, views.html(page))[0]


def answer_page(params) -> str:
    """The HTML page that writes exactly what a test with these params asks for (`test_invariants.answer`)."""
    return answer(types.SimpleNamespace(params=params))["html"]
