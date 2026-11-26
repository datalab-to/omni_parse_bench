# ruff: noqa: E501
"""Relations of `region` tests (M150 to M159): a region the page leaves as printed passes however it is
written and wherever it sits, fails once anything is added to it or taken from it, and keeps its verdict
when the page changes outside it."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, every_real_test, more_evidence, passes, relation, text_strings
from metamorphic.test_blank_fields import MARKDOWN, OTHERS, fields_of, in_cell, one_line, paragraphs, read_across, two_columns, two_columns_th
from omni_parse_bench import normalize, views
from omni_parse_bench.scorers.unit_tests import runners

TARGET, NEXT = "Date of birth:", "Place of birth:"
OTHER_LABELS = [x for x in OTHERS if x != NEXT]        # the fields the target's region may follow


def field_test(content: str | None = None, md: int = 0) -> runners.Region:
    """The target field's region: from its label to the next field's label."""
    return runners.Region(TARGET, NEXT, content, md)


def form(order, k, value, shown=None):
    """The form with the target at position k among the others in `order`, `Place of birth:` right after it
    (so the region is the target's own field)."""
    fields = fields_of(order, k, value, shown=shown)
    fields.insert(k + 1, (NEXT, (shown or {}).get(NEXT, OTHERS[NEXT])))
    return fields


# Note: the layouts that write a field's label before its value in reading order. A header-row table writes
# every label before any value, so it is no region (docs/scoring/region.md, case rg-header-row).
LAYOUTS = {"paragraphs": paragraphs, "one line": one_line, "two columns": two_columns,
           "two columns th": two_columns_th, "read across": read_across, "label and value in one cell": in_cell,
           **MARKDOWN}
BLANKS = ["", " ", "&nbsp;", "<br>", "<br><br>", "\n\n", "____", ".....", "…", "<span></span>", "<b></b>",
          "<input type=text>", "<p></p>", "​", "<img alt='a signature'>", "<math></math>"]
MD_BLANKS = ["", " ", "____", ".....", "…"]
TOKENS = ["x", "0", "N/A", "1990", "a b", "none", "1/2", "é", "中", "Paris", "[blank]", "-x", "☐"]
LAYOUT = st.sampled_from(list(LAYOUTS))
FIELD = st.integers(0, len(OTHER_LABELS))
ORDER = st.permutations(OTHER_LABELS)
CASE = st.sampled_from(["as printed", "upper", "lower"])


def blanks_for(layout: str) -> list[str]:
    return MD_BLANKS if layout in MARKDOWN else BLANKS


# ------------------------------------------------------------------------------------------ what passes


@relation(HOLDS, domain="8 layouts x 16 spellings of a blank (5 in markdown) x 4 positions x 6 orders of the "
                        "other fields x 3 cases of the labels")
@given(LAYOUT, st.data(), FIELD, ORDER, CASE)
def test_a_blank_region_passes_however_the_blank_is_written_in_every_layout(layout, data, k, order, case):
    """A blank field's region (from its label to the next label, holding nothing) passes when the field is
    written as nothing, white space, `&nbsp;`, line breaks, a line of underscores or dots, `…`, an empty
    element, an empty `<input>`, an empty `<math>`, a zero-width space or an image with a description, in a
    paragraph, a one-line form, a two-column table (`<td>` or `<th>` labels), a table read across, one cell per
    field, or markdown paragraphs or a pipe table, wherever the field sits and in any case of the labels.
    [M150]
    Why it matters for a score: a system that draws a blank field in any of these ways is graded as one that
    leaves it blank."""
    # Given a form whose target field is blank in one spelling, the labels in one case
    blank = data.draw(st.sampled_from(blanks_for(layout)))
    shape = {"as printed": str, "upper": str.upper, "lower": str.lower}[case]
    fields = [(shape(label), value) for label, value in form(order, k, blank)]
    # When it is written in a layout; Then the region passes
    page = LAYOUTS[layout](fields)
    assert passes(field_test(), page), (layout, page)


@relation(HOLDS, domain="5 respellings x 8 layouts; on 4 regions of known content (a caption, a sentence, a "
                        "table row, a mask)")
@given(st.sampled_from(["spaces", "entity", "markup", "case", "breaks"]), LAYOUT,
       st.sampled_from(["Results of the trial", "We study parsing. It is hard.", "Rent 100", "__/__/____"]))
def test_respelling_a_region_keeps_its_pass(how, layout, content):
    """A region whose content is written with other spacing, with `&nbsp;` for its spaces, inside inline
    markup, in another case, or with a line break between its words passes as the region written plainly does.
    [M155]
    Why it matters for a score: what the region holds is judged, not how its characters are spaced or
    styled."""
    # Given the region written plainly, passing
    test = field_test(content)
    words = content.split(" ")
    assert passes(test, LAYOUTS[layout](form(OTHER_LABELS, 1, escaped(content))))
    # When it is respelled
    value = {"spaces": "  ".join(words), "entity": "&nbsp;".join(words),
             "markup": f"<b>{escaped(words[0])}</b> <i>{escaped(' '.join(words[1:]))}</i>" if len(words) > 1 else f"<b>{escaped(content)}</b>",
             "case": content.upper(), "breaks": "<br>".join(words)}[how]
    if layout in MARKDOWN and how in ("markup", "breaks", "entity"):
        value = " ".join(words)     # (markdown has no tags; the respelling is the html one)
    # Then it still passes
    page = LAYOUTS[layout](form(OTHER_LABELS, 1, value))
    assert passes(test, page), (how, layout, page)


SPELLINGS = {"spaces": lambda x: x.replace(" ", "  "), "entity": lambda x: x.replace(" ", "&nbsp;"),
             "markup": lambda x: f"<b>{x.split(' ', 1)[0]}</b> {x.split(' ', 1)[1]}",
             "case": str.upper, "breaks": lambda x: x.replace(" ", "<br>", 1), "as printed": lambda x: x}
HTML_ONLY = {"entity", "markup", "breaks"}


@relation(HOLDS, domain="6 spellings of the start x 6 of the end x 8 layouts x 2 values (blank, filled); and "
                        "each anchor glued in turn")
@given(st.sampled_from(list(SPELLINGS)), st.sampled_from(list(SPELLINGS)), LAYOUT, st.booleans())
def test_an_anchor_is_found_however_it_is_spaced_or_styled_and_not_when_its_words_are_glued(at_start, at_end,
                                                                                            layout, filled):
    """The start and the end, each written with other spacing, `&nbsp;`, inline markup, in another case or with
    a line break between its words (the two ends spelled independently), give the verdict the anchors written as
    printed give: a blank field passes, a filled one fails. An anchor written with its words glued is not
    found. [M159]
    Why it matters for a score: an anchor is found under the one equivalence the page is read with, never under
    a second, looser search, so a region's ends are where the page prints them."""
    if layout in MARKDOWN:
        at_start, at_end = (x if x not in HTML_ONLY else "as printed" for x in (at_start, at_end))
    value = "1990" if filled else ""
    # Given the form, its target field blank or filled
    fields = form(OTHER_LABELS, 1, value)
    assert passes(field_test(), LAYOUTS[layout](fields)) is not filled
    # When its anchors are respelled; Then the verdict stays
    ends = {TARGET: SPELLINGS[at_start](TARGET), NEXT: SPELLINGS[at_end](NEXT)}
    page = LAYOUTS[layout]([(ends.get(label, label), v) for label, v in fields])
    assert passes(field_test(), page) is not filled, (at_start, at_end, layout, page)
    # When either anchor is glued; Then it is not found
    for glued in (TARGET, NEXT):
        page = LAYOUTS[layout]([(label.replace(" ", "") if label == glued else label, v) for label, v in fields])
        assert not passes(field_test(), page), (glued, layout, page)


# ------------------------------------------------------------------------------------------ what fails


@relation(HOLDS, domain="8 layouts x 16 blanks x 13 tokens x 3 places in the field x 4 positions x 6 orders")
@given(LAYOUT, st.data(), st.sampled_from(TOKENS), st.sampled_from(["before", "after", "alone"]), FIELD, ORDER)
def test_any_letter_or_digit_token_added_to_a_region_fails_it(layout, data, token, where, k, order):
    """A token with a letter or digit written in a blank region (before the blank, after it, or in its place:
    `N/A`, a date, a word, a checkbox) fails the region's test, in every layout and at every position, while
    the blank form passes. [M151]
    Why it matters for a score: an output that writes anything the page does not print in a closed region
    does not pass for leaving it as printed."""
    blank = data.draw(st.sampled_from(blanks_for(layout)))
    # Given the blank form passes
    assert passes(field_test(), LAYOUTS[layout](form(order, k, blank)))
    # When a token is written in the field; Then it fails
    value = {"before": f"{token} {blank}", "after": f"{blank} {token}", "alone": token}[where]
    page = LAYOUTS[layout](form(order, k, value))
    assert not passes(field_test(), page), (layout, value, page)


@more_evidence()
@given(st.sampled_from(["second cell", "cell below", "second table", "paragraph after the table",
                        "nested table"]), st.sampled_from(TOKENS), st.sampled_from([None, "__/__/____"]))
def test_a_value_written_anywhere_between_the_anchors_fails(where, token, content):
    """A value written two cells right of the label, in the cell below it, in a second `<table>`, in a
    paragraph after `</table>` or in a nested table fails the region's test: the region runs in reading order
    across cells and tables, up to the end anchor. [M151]
    Why it matters for a score: the places a per-cell guard does not read are inside the region."""
    mask = content or ""
    t = escaped(token)
    page = {
        "second cell": f"<table><tr><td>{TARGET}</td><td>{mask}</td><td>{t}</td></tr><tr><td>{NEXT}</td><td>Paris</td></tr></table>",
        "cell below": f"<table><tr><td>{TARGET}</td><td>{mask}</td></tr><tr><td>{t}</td><td></td></tr><tr><td>{NEXT}</td><td>Paris</td></tr></table>",
        "second table": f"<table><tr><td>{TARGET}</td><td>{mask}</td></tr></table><table><tr><td>{t}</td></tr></table><p>{NEXT} Paris</p>",
        "paragraph after the table": f"<table><tr><td>{TARGET}</td><td>{mask}</td></tr></table><p>{t}</p><p>{NEXT} Paris</p>",
        "nested table": f"<table><tr><td>{TARGET}</td><td>{mask}<table><tr><td>{t}</td></tr></table></td></tr><tr><td>{NEXT}</td></tr></table>",
    }[where]
    assert passes(field_test(content), page.replace(t, "")), where
    assert not passes(field_test(content), page), (where, page)


@relation(HOLDS, domain="3 contents x 4 edits (a word dropped, a character dropped, a word doubled, a "
                        "number changed) x 2 budgets")
@given(st.sampled_from(["Results of the trial in 2019", "We study parsing. It is hard.", "Rent 100 Fuel 70"]),
       st.sampled_from(["drop word", "drop char", "double word", "number"]), st.sampled_from([0, 1]))
def test_text_taken_from_a_region_or_a_number_changed_fails(content, edit, md):
    """A region that loses a word, loses a character (with no edit to spend), doubles a word or changes a number
    (at any budget) fails, while the region as printed passes. [M152]
    Why it matters for a score: a region is compared as a whole, so a missing or changed part costs as an added
    one does."""
    test = runners.Region("Abstract", "Introduction", content, md)
    page = "<p>Abstract</p><p>{}</p><h2>Introduction</h2>"
    assert passes(test, page.format(escaped(content)))
    words = content.split(" ")
    changed = {"drop word": " ".join(words[1:]), "drop char": content[1:] if md == 0 else content[2:] + "zz",
               "double word": " ".join([words[0], *words]),
               "number": content.replace("2019", "2018").replace("100", "101").replace("parsing", "parsing 1")}[edit]
    assert not passes(test, page.format(escaped(changed))), (edit, changed)


# ------------------------------------------------------------------------------- copies, splits, outside


@relation(HOLDS, domain="8 layouts x 4 pairs of copies (blank or filled, in either order) x 13 tokens")
@given(LAYOUT, st.sampled_from([("", ""), ("", "x"), ("x", ""), ("x", "x")]), st.sampled_from(TOKENS))
def test_a_page_written_twice_passes_only_when_both_copies_are_right(layout, pair, token):
    """A form written twice passes the region's test when both copies leave the field blank, and fails when
    either copy fills it, whichever comes first. [M153]
    Why it matters for a score: a system cannot pass by writing one clean copy beside an invented one."""
    first, second = (token if x else "" for x in pair)
    page = LAYOUTS[layout](form(OTHER_LABELS, 1, first)) + LAYOUTS[layout](form(OTHER_LABELS, 1, second))
    assert passes(field_test(), page) is (pair == ("", "")), (layout, page)


ROWS = [("Rent", "100"), ("Fuel", "70"), ("Tax", "9"), ("Food", "250")]


@relation(HOLDS, domain="3 split points x 2 regions (across the table, after its end) x 2 states (as printed, "
                        "a row added)")
@given(st.integers(1, len(ROWS) - 1), st.sampled_from(["across", "after"]), st.booleans())
def test_splitting_a_table_in_two_keeps_the_verdict(at, which, added):
    """A table split into two `<table>`s at any row gives the verdict the whole table gives, for a region that
    runs across the table (from its caption to the next paragraph) and one that starts at its last cell; with a
    row added, both fail. [M154]
    Why it matters for a score: how a system cuts a table into elements does not decide a region's verdict."""
    rows = [*ROWS, ("Total", "429")] if added else ROWS
    cells = " ".join(f"{a} {b}" for a, b in ROWS)
    test = (runners.Region("Table 2. Costs", "The costs fell", cells, 0) if which == "across"
            else runners.Region("Food 250", "The costs fell", None, 0))
    tr = lambda rs: "".join(f"<tr><td>{a}</td><td>{b}</td></tr>" for a, b in rs)  # noqa: E731
    whole = f"<p>Table 2. Costs</p><table>{tr(rows)}</table><p>The costs fell.</p>"
    split = f"<p>Table 2. Costs</p><table>{tr(rows[:at])}</table><table>{tr(rows[at:])}</table><p>The costs fell.</p>"
    assert passes(test, whole) == passes(test, split) == (not added), (which, at, added)


@relation(HOLDS, domain="8 layouts x 13 tokens x 2 places outside (before the first field, after the next "
                        "field's value) x 2 states of the field")
@given(LAYOUT, st.sampled_from(TOKENS), st.sampled_from(["before", "after"]), st.sampled_from(["", "1990"]))
def test_text_added_outside_the_region_keeps_the_verdict(layout, token, where, value):
    """A token added before the form or after the field that ends the region keeps the region's verdict: a
    blank field passes and a filled one fails, whatever is written outside it. [M156]
    Why it matters for a score: a region judges its own stretch of the page, so text elsewhere (another
    field's value, a footer) never decides it."""
    # Given a form, its target blank or filled
    page = LAYOUTS[layout](form(OTHER_LABELS, 1, value))
    want = passes(field_test(), page)
    assert want is (value == "")
    # When a token is written outside the region; Then the verdict is the same
    extra = f"<p>{escaped(token)}</p>" if layout not in MARKDOWN else LAYOUTS[layout]([(token, "")])
    moved = extra + page if where == "before" else page + extra
    assert passes(field_test(), moved) is want, (layout, moved)


# ---------------------------------------------------------------------------------------- the loaded tests

STRING_LAYOUTS = {
    "paragraph": "<p>{s}</p><p>{x}</p><p>{e}</p>", "inline": "<p>{s} {x} {e}</p>",
    "table cell": "<p>{s}</p><table><tr><td>{x}</td></tr></table><p>{e}</p>",
    "list item": "<p>{s}</p><ul><li>{x}</li></ul><p>{e}</p>",
}
ANCHORS = ("§ region start §", "§ region end §")


@relation(HOLDS, domain="every text string of the loaded tests x 4 layouts x 5 pages (as written, a word "
                        "with a digit inside, a word of letters inside, a letter inside a word, the word outside)",
          pool="text, order, repeat, table_cell")
def test_every_loaded_text_string_as_a_region_passes_as_written_and_fails_with_a_token_added():
    """Each text string of the loaded text, order, repeat and table_cell tests, made a region's content between
    two anchors, passes when written between them as a paragraph, inline, in a table cell or in a list item;
    fails with a word added inside the region (one with a digit, one of letters only) or a letter added in its
    middle; and passes with the word added outside it. [M157]
    Why it matters for a score: the whole-string comparison meets the dataset's own strings (its fold, its
    spacing, its bullets and numbers), not only generated words."""
    start, end = ANCHORS
    n, bad = 0, []
    for t in TESTS:
        for x in text_strings(t.params):
            if not normalize.fold(x):
                continue
            n += 1
            test = runners.Region(start, end, x, 0)
            for name, layout in STRING_LAYOUTS.items():
                fill = lambda y, layout=layout: layout.format(s=start, x=y, e=end)  # noqa: E731
                if not passes(test, fill(escaped(x))):
                    bad.append((t.id, name, "as written"))
                if passes(test, fill(f"{escaped(x)} zq7")):
                    bad.append((t.id, name, "token inside"))
                if passes(test, fill(f"{escaped(x)} zq")):
                    bad.append((t.id, name, "letters inside"))
                mid = len(x) // 2
                if passes(test, fill(escaped(f"{x[:mid]}q{x[mid:]}"))):
                    bad.append((t.id, name, "a letter inside"))
                if not passes(test, f"<p>zq7</p>{fill(escaped(x))}<p>zq7</p>"):
                    bad.append((t.id, name, "token outside"))
    assert n, "no loaded text string"
    assert not bad, f"{len(bad)} of {n * 20} cases break, e.g. {bad[:5]}"


@more_evidence()
def test_the_helpers_build_the_regions_they_say():
    """A form in each layout holds the target's label right before the next field's label in reading order,
    each label once. [M150, M151]
    Why it matters for a score: the relations above test what they claim to."""
    for name, make in LAYOUTS.items():
        page = views.html(make(form(OTHER_LABELS, 1, "1990"))).seen
        assert page.count(TARGET) == 1 and page.count(NEXT) == 1, name
        assert page.index(TARGET) < page.index("1990") < page.index(NEXT), name


# ------------------------------------------------------------------- other test types are unchanged

OLD_COMMIT = "cf19df3"    # main before `region`
ROOT = Path(__file__).resolve().parents[2]
RUNNER = """
import json, sys
sys.path.insert(0, sys.argv[1])
from omni_parse_bench import score
from omni_parse_bench.scorers.unit_tests import tests as gold
out = []
for test, html in json.load(sys.stdin):
    [v] = score({"html": html}, [gold.test("p", test)])
    out.append([v.result, v.why])
json.dump(out, sys.stdout)
"""


BASELINE = Path(__file__).parent / "region_old_verdicts.json"


@pytest.fixture(scope="module")
def old_package(tmp_path_factory):
    """The package at OLD_COMMIT, checked out from git into a folder of its own and run in a subprocess, so it
    shares no code with the working tree. A checkout without that commit fails: fetch the full history
    (`git fetch --unshallow`)."""
    if subprocess.run(["git", "cat-file", "-e", OLD_COMMIT], cwd=ROOT, capture_output=True).returncode:
        pytest.fail(f"needs git history holding {OLD_COMMIT}: run `git fetch --unshallow`")
    where = tmp_path_factory.mktemp("old")
    tar = subprocess.run(["git", "archive", OLD_COMMIT, "omni_parse_bench"], cwd=ROOT, check=True,
                         capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(where)], input=tar, check=True)
    return where


def _cases(tests) -> list[tuple[dict, str]]:
    """Each loaded html test as its gold dict, on its own answer, the answer with its last character dropped,
    the answer with a word after it, and an empty page."""
    from test_invariants import answer
    out = []
    for t in tests:
        got = answer(t)
        if "html" not in got:
            continue
        test = {"id": t.id, "test_type": t.test_type, "output_type": t.output_type, "derivation": t.derivation,
                "tags": list(t.tags), "args": t.args, "settings": t.settings}
        page = got["html"]
        for html in (page, page[:-5] + page[-4:] if page.endswith("</p>") else page[:-1], page + "<p>x</p>", ""):
            out.append((test, html))
    return out


def _compare(old_package, cases) -> None:
    from omni_parse_bench import score
    from omni_parse_bench.scorers.unit_tests import tests as gold
    done = subprocess.run([sys.executable, "-I", "-c", RUNNER, str(old_package)], input=json.dumps(cases),
                          check=True, capture_output=True, text=True).stdout
    old = [tuple(x) for x in json.loads(done)]
    new = [(v.result, v.why) for test, html in cases for v in score({"html": html}, [gold.test("p", test)])]
    differ = [(c[0]["id"], c[1][:60], o, n) for c, o, n in zip(cases, old, new, strict=True) if o != n]
    assert not differ, f"{len(differ)}/{len(cases)} differ, e.g. {differ[:3]}"
    assert {n[0] for n in new} == {"pass", "fail"}, "the cases hold both verdicts"


@relation(HOLDS, domain="136 frozen cases: the 34 html tests of tests/fixtures/invariants/ at cf19df3 x 4 pages "
                        "(its answer, a character dropped, a word added, an empty page)")
def test_every_frozen_case_of_another_type_keeps_its_verdict():
    """Each frozen case (a fixture test of a type older than `region`, on its answer, the answer with a character
    dropped, the answer and a word, and an empty page) gets the verdict and the why that the package at cf19df3
    gave it, recorded in region_old_verdicts.json. [M158]
    Why it matters for a score: the new test type changes no existing test's verdict."""
    from omni_parse_bench import score
    from omni_parse_bench.scorers.unit_tests import tests as gold
    rows = json.loads(BASELINE.read_text())
    # Note: recorded by running `_cases` over the fixtures in the package at OLD_COMMIT (RUNNER); frozen so that
    # a type added later never reaches the old package, which could not read it
    assert len(rows) == 136 and {r["result"] for r in rows} == {"pass", "fail"}
    assert not {r["test"]["test_type"] for r in rows} - {"present", "format", "repeat", "table_cell", "order",
                                                          "page_near_empty", "layout_kind"}
    differ = [(r["test"]["id"], r["html"][:60], (r["result"], r["why"]), (v.result, v.why)) for r in rows
              for v in score({"html": r["html"]}, [gold.test("p", r["test"])]) if (v.result, v.why) != (r["result"], r["why"])]
    assert not differ, f"{len(differ)}/{len(rows)} differ, e.g. {differ[:3]}"


@every_real_test("text tests", note="each on its answer, the answer altered, the answer and a word, and an "
                                    "empty page; old package against new")
def test_every_real_test_keeps_its_old_verdict(old_package):
    """Every real text, order, repeat and table_cell test gets the verdict and the why that the package at cf19df3
    gives on four pages, as in the check above, run from git in a subprocess; a checkout without cf19df3 fails
    rather than skips. [M158]
    Why it matters for a score: as for M158, over the dataset's own tests."""
    from metamorphic.common import CELL, ORDER, REPEAT, TEXT
    _compare(old_package, _cases([*TEXT, *ORDER, *REPEAT, *CELL]))
