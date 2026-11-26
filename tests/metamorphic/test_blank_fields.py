# ruff: noqa: E501
"""Relations of `present` tests with `{"blank_after": true}` (M98 to M103): a form field the page leaves blank
passes however the blank is written and wherever the field sits, and fails once anything is written in it."""
from __future__ import annotations

import json
import random
import string
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import (HOLDS, escaped, every_real_test, more_evidence, passes,
                                relation)
from omni_parse_bench import markdown, views
from omni_parse_bench.scorers.unit_tests import runners

TARGET, MASK = "Date of birth:", "__/__/____"
OTHERS = {"Name:": "Ann Lee", "Place of birth:": "Paris", "Phone:": "555 0101", "Email:": "ann at example.org"}


def blank_test(labels=tuple(OTHERS), label=TARGET) -> runners.Present:
    """The field's test: its label, its printed mask, and the other fields' labels as stops."""
    return runners.Present(runners.Text(label, 0), True, runners.Text(MASK, 0),
                           tuple(runners.Text(x, 0) for x in labels))


def plain_test(label=TARGET) -> runners.Present:
    return runners.Present(runners.Text(label, 0))


# ------------------------------------------------------------------------------------------ the layouts


def paragraphs(fields):
    return "".join(f"<p>{label} {value}</p>" for label, value in fields)


def one_line(fields):
    return "<p>" + " ".join(f"{label} {value}" for label, value in fields) + "</p>"


def two_columns(fields):
    return "<table>" + "".join(f"<tr><td>{label}</td><td>{value}</td></tr>" for label, value in fields) + "</table>"


def two_columns_th(fields):
    return "<table>" + "".join(f"<tr><th>{label}</th><td>{value}</td></tr>" for label, value in fields) + "</table>"


def header_row(fields):
    return ("<table><tr>" + "".join(f"<td>{label}</td>" for label, _ in fields) + "</tr><tr>"
            + "".join(f"<td>{value}</td>" for _, value in fields) + "</tr></table>")


def read_across(fields):
    rows = [fields[i:i + 2] for i in range(0, len(fields), 2)]
    return "<table>" + "".join("<tr>" + "".join(f"<td>{label}</td><td>{value}</td>" for label, value in row)
                               + "</tr>" for row in rows) + "</table>"


def in_cell(fields):
    """Each field in a cell of its own: the label and its value in one cell."""
    return "<table>" + "".join(f"<tr><td>{label} {value}</td></tr>" for label, value in fields) + "</table>"


def md_paragraphs(fields):
    return markdown.to_html("\n\n".join(f"{label} {value}" for label, value in fields))


def md_pipe(fields):
    return markdown.to_html("| field | value |\n|---|---|\n" + "\n".join(
        f"| {label} | {value} |" for label, value in fields))


LAYOUTS = {"paragraphs": paragraphs, "one line": one_line, "two columns": two_columns,
           "two columns th": two_columns_th, "header row": header_row, "read across": read_across,
           "label and value in one cell": in_cell}
MARKDOWN = {"markdown paragraphs": md_paragraphs, "markdown pipe table": md_pipe}
BLANKS = ["", " ", "&nbsp;", "<br>", "<br><br>", "\n\n", "____", ".....", "_", "..", "…", "·", MASK,
          f"{MASK} ____", f" {MASK} ", "<span></span>", "<b></b>", "<input type=text>",
          "<p></p>", "_ _ _", "__"]
PLAIN_BLANKS = ["", " ", "____", ".....", "_", "..", "…"]
TOKENS = ["x", "0", "N/A", "1990", "a b", "none", "1/2", "é", "中", "Paris", "[blank]x"]

FIELD = st.integers(0, len(OTHERS))                  # where the target sits among the others
ORDER = st.permutations(list(OTHERS))
LAYOUT = st.sampled_from(list(LAYOUTS))


def fields_of(order, k, value, label=TARGET, shown=None):
    """The others in `order` with the target, holding `value`, inserted at position k; each other field holds
    its own value (`shown` replaces one's)."""
    got = [(x, (shown or {}).get(x, OTHERS[x])) for x in order]
    got.insert(k, (label, value))
    return got


# ------------------------------------------------------------------------------------- blank spellings


@relation(HOLDS, domain="7 layouts x 21 spellings of a blank x 5 positions x 24 orders of the other fields x "
                        "3 cases of the labels")
@given(LAYOUT, st.sampled_from(BLANKS), FIELD, ORDER, st.sampled_from(["as printed", "upper", "lower"]))
def test_every_spelling_of_a_blank_field_passes_in_every_layout(layout, blank, k, order, case):
    """A form field written as nothing, white space, `&nbsp;`, `<br>`, a run of underscores or dots (also two, or
    spaced), `…`, a middle dot, the printed mask (once, also with a leader), an empty element or an empty
    `<input>` passes its `blank_after` test, in a paragraph, a one-line form, a
    two-column table (`<td>` or `<th>` labels), a header-row table, a table read across or one cell per
    field, wherever the field sits among the others and in any case of the labels. [M98]
    Why it matters for a score: a system that draws a blank field in any of these ways is graded as one that
    leaves it blank."""
    # Given a form of five fields, the target blank in one spelling at one position, the labels in one case
    shape = {"as printed": str, "upper": str.upper, "lower": str.lower}[case]
    fields = [(shape(label), value) for label, value in fields_of(order, k, blank)]
    # When it is written in a layout; Then the test passes
    page = LAYOUTS[layout](fields)
    assert passes(blank_test(), page), (layout, page)


@more_evidence()
@given(st.sampled_from(list(MARKDOWN)), st.sampled_from(PLAIN_BLANKS), FIELD, ORDER)
def test_a_blank_field_in_markdown_passes_and_a_filled_one_fails_as_in_html(layout, blank, k, order):
    """A blank field written in markdown (paragraphs, or a pipe table) passes its `blank_after` test, and the same
    field with a value written in fails it: the verdicts are those of the html the harness converts it to, and
    those of the html written by hand. [M98]
    Why it matters for a score: a system that answers in markdown is graded as one that answers in html."""
    # Given a form with the target blank, or holding 1990, in markdown
    for value, want in ((blank, True), (f"{blank} 1990".strip(), False)):
        markdown_page = MARKDOWN[layout](fields_of(order, k, value))
        # When the harness converts it; Then it passes or fails as the same form in html does
        assert passes(blank_test(), markdown_page) is want, (layout, value, markdown_page)
    html_page = LAYOUTS["paragraphs" if layout == "markdown paragraphs" else "two columns"](
        fields_of(order, k, blank))
    assert passes(blank_test(), html_page)


# -------------------------------------------------------------------------------------- what flips it


@relation(HOLDS, domain="7 layouts x 21 spellings x 11 tokens x 3 places in the field x 5 positions x 24 orders")
@given(LAYOUT, st.sampled_from(BLANKS), st.sampled_from(TOKENS), st.sampled_from(["before", "after", "alone"]),
       FIELD, ORDER)
def test_any_letter_or_digit_token_written_in_a_blank_field_fails_in_every_layout(layout, blank, token, where, k,
                                                                                   order):
    """A token with a letter or digit written in a blank field (before the blank, after it, or in its place:
    `N/A`, a date, an invented word) fails its `blank_after` test, in every layout and at every position,
    while the blank form passes. [M99]
    Why it matters for a score: an output that fills in a field the page leaves blank does not pass for
    leaving it blank."""
    # Given the blank form passes
    assert passes(blank_test(), LAYOUTS[layout](fields_of(order, k, blank)))
    # When a token is written in the field; Then it fails
    value = {"before": f"{token} {blank}", "after": f"{blank} {token}", "alone": token}[where]
    page = LAYOUTS[layout](fields_of(order, k, value))
    assert not passes(blank_test(), page), (layout, value, page)


@relation(HOLDS, domain="7 layouts x 4 positions x 24 orders; the next field's value shifted into the blank, and "
                        "a value written under the label in a header-row table")
@given(LAYOUT, st.integers(0, len(OTHERS) - 1), ORDER)
def test_the_next_fields_value_shifted_into_a_blank_field_fails(layout, k, order):
    """The value of the field after the target written in the target's place, with that field left blank (the
    values shifted one field up), fails the target's `blank_after` test in every layout (for a header-row table
    this is a value under the label), while the unshifted form passes. [M100]
    Why it matters for a score: a system that misaligns a form's values does not pass for leaving a field
    blank."""
    # Given the target at position k, blank, with another field after it holding a value
    after = order[k]
    blank = fields_of(order, k, "")
    assert passes(blank_test(), LAYOUTS[layout](blank))
    # When that field's value moves up into the target and the field is left blank
    shifted = fields_of(order, k, OTHERS[after], shown={after: ""})
    # Then the target fails
    assert not passes(blank_test(), LAYOUTS[layout](shifted)), (layout, LAYOUTS[layout](shifted))


@relation(HOLDS, domain="7 layouts x 5 positions x 5 positions x 24 orders x 2 states of the field")
@given(LAYOUT, FIELD, FIELD, ORDER, st.sampled_from(["", "1990"]))
def test_moving_another_field_keeps_the_verdict(layout, k, j, order, value):
    """Moving another whole field elsewhere on the page (before the target, after it, to another row or column)
    keeps the verdict of a `blank_after` test: a blank field passes and a filled one fails wherever the others
    are written. [M101]
    Why it matters for a score: the order in which a system reads a form does not decide a field's verdict."""
    # Given a form, and the same form with its fields in another order (the others moved, the target kept)
    first = fields_of(order, k, value)
    moved = list(order)
    moved.insert(j % len(moved), moved.pop(0))
    second = fields_of(moved, k, value)
    # When both are written in a layout; Then the verdicts are equal, and are those of the field's state
    one = passes(blank_test(), LAYOUTS[layout](first))
    other = passes(blank_test(), LAYOUTS[layout](second))
    assert one == other == (value == ""), (layout, first, second)


# ------------------------------------------------------------------------------------ only adds failures


@relation(HOLDS, domain="7 layouts x 40 values x 5 positions x 24 orders x 3 labels (the field's, one with a "
                        "typo, a missing one)")
@given(LAYOUT, st.sampled_from(BLANKS + TOKENS), FIELD, ORDER, st.sampled_from([TARGET, "Date of birt:", "Date:"]))
def test_a_blank_after_pass_is_a_plain_present_pass(layout, value, k, order, label):
    """A page that passes a `blank_after` test passes the same test without the setting (a plain `present` of
    its label), on every layout and every value, with the label right, mistyped or missing. [M102]
    Why it matters for a score: the setting only adds failures; no output passes it that plain `present`
    would fail."""
    # Given a form in a layout, the target written with one value
    page = LAYOUTS[layout](fields_of(order, k, value))
    # When `blank_after` passes; Then plain `present` of the same label passes too
    if passes(blank_test(label=label), page):
        assert passes(plain_test(label), page), (layout, value, page)
    # And a page the label is not on fails `blank_after`
    if not passes(plain_test(label), page):
        assert not passes(blank_test(label=label), page)


@every_real_test("exact text", note="each as a blank_after label, on pages of four shapes")
def test_every_real_exact_text_passes_blank_after_only_where_plain_present_does():
    """Every real exact text test (`max_diffs` 0), made a `blank_after` test of its text, passes only pages
    where plain `present` passes, on four pages: the text alone, the text and a word, the text in a table cell
    with an empty cell beside it, and the text with a value in that cell. [M102]
    Why it matters for a score: as for M102, over the dataset's own strings."""
    from metamorphic.test_fold_and_case import EXACT
    both = 0
    for t in EXACT:
        text = t.params.content.text
        pages = [f"<p>{escaped(text)}</p>", f"<p>{escaped(text)} x</p>",
                 f"<table><tr><td>{escaped(text)}</td><td></td></tr></table>",
                 f"<table><tr><td>{escaped(text)}</td><td>x</td></tr></table>"]
        for page in pages:
            blank = runners.Present(runners.Text(text, 0), True)
            if passes(blank, page):
                assert passes(runners.Present(runners.Text(text, 0)), page), (t.id, page)
                both += 1
    assert both, "no real test passes blank_after: the check is empty"


# ------------------------------------------------------------------- a test without the setting is unchanged

OLD_COMMIT = "222f0cd"    # main before `blank_after`
ROOT = Path(__file__).resolve().parents[2]
RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from omni_parse_bench import views
from omni_parse_bench.scorers.unit_tests import runners
out = []
for kind, value, max_diffs, exact, page in json.load(sys.stdin):
    arg = {"text": lambda: runners.Text(value, max_diffs, (), exact), "number": lambda: runners.Number(value),
           "latex": lambda: runners.Latex(value)}[kind]()
    out.append(list(runners.present(runners.Present(arg), views.html(page))))
json.dump(out, sys.stdout)
"""


@pytest.fixture(scope="module")
def old_package(tmp_path_factory):
    """The package at OLD_COMMIT, checked out from git into a folder of its own and run in a subprocess, so it
    shares no code with the working tree. Skipped when the history does not hold that commit."""
    if subprocess.run(["git", "cat-file", "-e", OLD_COMMIT], cwd=ROOT, capture_output=True).returncode:
        pytest.skip(f"needs git history holding {OLD_COMMIT}")
    where = tmp_path_factory.mktemp("old")
    tar = subprocess.run(["git", "archive", OLD_COMMIT, "omni_parse_bench"], cwd=ROOT, check=True,
                         capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(where)], input=tar, check=True)
    return where


def old_present(old_package, cases) -> list[tuple[bool, str]]:
    """The old package's `present` verdict and why for each (kind, value, max_diffs, exact, page)."""
    done = subprocess.run([sys.executable, "-I", "-c", RUNNER, str(old_package)], input=json.dumps(cases),
                          check=True, capture_output=True, text=True).stdout
    return [tuple(x) for x in json.loads(done)]


def new_present(cases) -> list[tuple[bool, str]]:
    return [tuple(runners.present(runners.Present(arg_of(*c[:4])), views.html(c[4]))) for c in cases]


def arg_of(kind, value, max_diffs, exact):
    """The content arg of a (kind, value, max_diffs, exact) case."""
    if kind == "text":
        return runners.Text(value, max_diffs, (), exact)
    return runners.Number(value) if kind == "number" else runners.Latex(value)


@relation(HOLDS, domain="300 random text tests (0 to 2 edits, either case rule) on 6 pages each, 1,800 in all; "
                        "needs git history holding 222f0cd")
def test_a_present_test_without_blank_after_gives_the_verdict_it_gave_before(old_package):
    """A `present` test with no `blank_after` setting gets the verdict and the why that the package at 222f0cd
    gives (run from git in a subprocess, sharing no code), on 300 random text tests of letters, digits and
    leaders, each on its own text, an altered copy, a label-and-blank form, a filled form, a table and a
    word-edged copy (1,800 cases). [M103]
    Why it matters for a score: the new setting and its roles change no existing test's score."""
    # Given random present text tests and pages built from their strings, in forms and tables
    rnd = random.Random(103)
    word = lambda: "".join(rnd.choices(string.ascii_letters + string.digits + " :", k=rnd.randint(3, 9)))  # noqa: E731
    cases = []
    for _ in range(300):
        text, other = word().strip() or "abc", word()
        exact = rnd.random() < 0.2
        md = 0 if exact else rnd.choice([0, 0, 1, 2])
        for page in (f"<p>{escaped(text)}</p>", f"<p>{escaped(text[:-1] + 'x')}</p>",
                     f"<p>{escaped(text)} ____ {escaped(other)}</p>", f"<p>{escaped(text)} 1990</p>",
                     f"<table><tr><td>{escaped(text)}</td><td></td></tr><tr><td>{escaped(other)}</td></tr></table>",
                     f"<p>x{escaped(text)}y {escaped(other)}</p>"):
            cases.append(("text", text, md if len(text) > md else 0, exact, page))
    # When the old package and this one grade them; Then the verdicts and the whys are equal
    old, new = old_present(old_package, cases), new_present(cases)
    differ = [(c, o, n) for c, o, n in zip(cases, old, new, strict=True) if o != n]
    assert not differ, f"{len(differ)}/{len(cases)} differ, e.g. {differ[:2]}"
    assert {n[0] for n in new} == {True, False}, "the cases hold both verdicts"


@every_real_test("present tests", note="a page built for each, and altered pages, old package against new")
def test_every_real_present_test_keeps_its_old_verdict(old_package):
    """Every real present test (none has the `blank_after` setting) gets the verdict and the why that the
    package at 222f0cd gives, on a page that holds its content, one with a letter changed, one with a word
    after it and one with it in a table cell: text, number and equation tests alike. [M103]
    Why it matters for a score: as for M103, over the dataset's own tests."""
    from metamorphic.common import TESTS
    cases = []
    for t in TESTS:
        p = t.params
        if not isinstance(p, runners.Present):
            continue
        c = p.content
        kind, value = ("text", c.text) if isinstance(c, runners.Text) else (
            ("number", c.number) if isinstance(c, runners.Number) else ("latex", c.latex))
        shown = f"$${value}$$" if kind == "latex" else escaped(value)
        exact, md = (c.exact_case, c.max_diffs) if kind == "text" else (False, 0)
        for page in (f"<p>{shown}</p>", f"<p>{shown[:-1]}</p>", f"<p>{shown} x</p>",
                     f"<table><tr><td>{shown}</td><td></td></tr></table>"):
            cases.append((kind, value, md, exact, page))
    old, new = old_present(old_package, cases), new_present(cases)
    differ = [(c[:3], c[4][:60]) for c, o, n in zip(cases, old, new, strict=True) if o != n]
    assert not differ, f"{len(differ)}/{len(cases)} differ, e.g. {differ[:5]}"


@more_evidence()
def test_the_helpers_build_the_pages_they_say():
    """A form in each layout holds each label and its value once, and the markdown ones convert to a table or to
    paragraphs. [M98, M99]
    Why it matters for a score: the relations above test what they claim to."""
    fields = fields_of(list(OTHERS), 2, "1990")
    for name, make in {**LAYOUTS, **MARKDOWN}.items():
        text = views.html(make(fields)).text
        for label, value in fields:
            assert text.count(label) == 1 and value in text, (name, label)
