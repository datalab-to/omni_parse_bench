"""Relations of fold (M1, M2), of deleting a character (M14) and of the case of a page (M15)."""
from __future__ import annotations

import collections
import re
import string
import unicodedata

from hypothesis import assume, example, given
from hypothesis import strategies as st
from test_properties import TESTS

from metamorphic.common import (CELL, HOLDS, INTENDED, LIMITATION, ORDER, REPEAT, TEXT, answer_page,
                                deviation, escaped, every_real_test, known_ids, more_evidence, passes,
                                relation, text_strings)
from omni_parse_bench import views
from omni_parse_bench.normalize import fold
from omni_parse_bench.scorers.unit_tests import runners

LINE_END_HYPHEN = re.compile(r"[^\W\d_]-\s")    # a letter, a hyphen, a space: what fold may join
LINE_END_HYPHEN_ANY = re.compile(r"[^\W\d_][-\u2010\u2011]\s")    # the same, with the Unicode hyphens
ALPHABET = string.ascii_letters + string.digits + "éüñàçöå"
WORD = st.text(ALPHABET, min_size=1, max_size=6)
PROSE = st.lists(st.one_of(WORD, st.sampled_from(["AT&T", "R&D", "Q&A", "&", "a&b"]),
                           st.sampled_from([".", ",", "-", "(x)", "50%", "1,000"])),
                 min_size=1, max_size=8).map(" ".join)

# ------------------------------------------------------------------------------------- fold twice


@relation(LIMITATION)
@deviation("M1a")
@example("a- B")
@given(st.text(string.ascii_letters + " -"))
def test_folding_twice_is_folding_once_with_hyphens(s):
    """Folding a string of letters, spaces and hyphens twice gives the same text as folding it once. [M1a]
    Why it matters for a score: the gold and the page are each folded once; a second fold that changes the
    text shows that the folded form is not final."""
    # Given a string s; When it is folded once and twice; Then both give the same text.
    assert fold(fold(s)) == fold(s)


@relation(LIMITATION)
@deviation("M1b")
@example("y\u2014 t")
@example("hereditary\u2014 everyone")
@example("Intellectual\u2013 cultural")
@given(st.text(string.ascii_letters + " \u2014\u2013"))    # em dash, en dash
def test_folding_twice_is_folding_once_with_dashes(s):
    """Folding letters, spaces and dashes (no hyphen) twice gives the same text as folding them once. [M1b]
    Why it matters for a score: as for M1a, for a dash at the end of a line."""
    # Given a string s with dashes and no line-end hyphen (that is M1a)
    assume(not LINE_END_HYPHEN.search(s))
    # When it is folded once and twice; Then both give the same text
    assert fold(fold(s)) == fold(s)


@relation(LIMITATION)
@deviation("M1c")
@example("[...]")
@example("[ . . . ]")
@given(st.text(" .[]x", min_size=1))
def test_folding_twice_is_folding_once_with_brackets_and_dots(s):
    """Folding a string of brackets, dots, spaces and x twice gives the same text as folding it once. [M1c]
    Why it matters for a score: as for M1a, where a checkbox ('[ ]', '[x]') and a leader ('...') meet."""
    # Given a string s of box and leader characters; When it is folded once and twice; Then both are the same
    assert fold(fold(s)) == fold(s)


@relation(HOLDS)
@example("'\u2019")
@given(st.text("a '\u2019\u2018`\""))
def test_folding_twice_is_folding_once_with_quotes(s):
    """Folding a string of single quotes (`'`, `\u2018`, `\u2019`, a backtick), double quotes, `a` and spaces
    twice gives the same text as folding it once. [M1d]
    Why it matters for a score: TeX writes a double quote as two single quotes, and a page may mix their
    forms: a gold written '' must match a page that writes '\u2019."""
    # Given a string s of quotes; When it is folded once and twice; Then both give the same text
    assert fold(fold(s)) == fold(s)


@relation(LIMITATION)
@deviation("M1e")
@example("\u2022 \u2022")
@given(st.text("a \u2022"))
def test_folding_twice_is_folding_once_with_bullets(s):
    """Folding a string of bullets (`\u2022`), `a` and spaces twice gives the same text as folding it once.
    [M1e]
    Why it matters for a score: as for M1a, where a bullet inside a line comes to start it."""
    # Given a string s of bullets; When it is folded once and twice; Then both give the same text
    assert fold(fold(s)) == fold(s)


BULLETS = "[•‣◦▪▶∙●]"    # the glyphs fold removes at a line start
# What a real string that folds differently twice shows, by relation: the shape of M1a to M1e.
FOLD_TWICE_SHAPE = {"M1a": re.compile(r"[^\W\d_][-\u2010\u2011]\s+[^\W\d_]"),   # hyphen, space, letter
                    "M1b": re.compile(r"[\u2013\u2014]\s+[^\W\d_]"),               # dash, space, letter
                    "M1c": re.compile(r"\[[\s.\u2026]*\]"),                       # brackets round dots
                    "M1d": re.compile("['\u2018\u2019`]{2}"),                     # two single quotes
                    "M1e": re.compile(rf"{BULLETS}\s+{BULLETS}")}                     # two bullets


@every_real_test("text strings")
def test_every_real_text_string_folds_to_the_same_text_twice():
    """Every real text string folds to the same text twice as once, except the ones listed. [M1a, M1b, M1c,
    M1d, M1e]
    Why it matters for a score: it counts how many real strings each deviation above touches."""
    # Given every text string of every real test, named `<test id>#<position>`
    # When each is folded once and twice, and each one that changes is sorted by its shape
    changed = collections.defaultdict(set)
    for t in TESTS:
        for n, x in enumerate(text_strings(t.params)):
            if fold(fold(x)) != fold(x):
                shapes = [label for label, shape in FOLD_TWICE_SHAPE.items() if shape.search(x)]
                changed[shapes[0] if len(shapes) == 1 else f"unsorted {shapes}"].add(f"{t.id}#{n}")
    # Then each relation's strings are exactly the ones known_deviations.json lists for it
    for label in FOLD_TWICE_SHAPE:
        found, known = changed.pop(label, set()), known_ids(label)
        assert found == known, (label, {"new": sorted(found - known), "gone": sorted(known - found)})
    assert not changed, changed

# ---------------------------------------------------------------------------- what fold ignores


@relation(HOLDS)
@given(PROSE)
def test_fold_ignores_case(s):
    """Fold gives the same text in upper, lower or swapped case for text made of words (ASCII letters, digits
    and éüñàçöå), '&' words (AT&T) and the marks . , - (x) 50% 1,000; no line-end hyphen. [M2a]
    Why it matters for a score: a page that prints a heading in capitals passes the test of the same words."""
    # Given ordinary text with no line-end hyphen (whose reading depends on case in mixed case: M2e)
    assume(not LINE_END_HYPHEN.search(s))
    # When it is folded in upper case, as written, in lower case and swapped; Then all four are the same
    assert fold(s.upper()) == fold(s) == fold(s.lower()) == fold(s.swapcase())


@relation(HOLDS)
@example(s="RE- M")
@example(s="Anglo- Saxon")
@given(st.lists(st.one_of(WORD, st.sampled_from(["a-", "Re-", "ab-", "-"])), min_size=2, max_size=6)
       .map(" ".join))
def test_fold_ignores_case_at_a_line_end_hyphen(s):
    """Fold gives the same text for words ending in a hyphen in upper case and in lower case. [M2e]
    Why it matters for a score: as for M2a, at a word broken at the end of a line: a heading in capitals
    broken across a line reads as the same words in lower case."""
    # Given words, some ending in a hyphen; When folded in upper case and in lower case
    # Then both are the same (in mixed case a capital after the hyphen keeps it, by the documented rule)
    assert fold(s.upper()) == fold(s.lower())


@relation(HOLDS)
@given(PROSE, st.data())
def test_fold_ignores_runs_of_whitespace(s, data):
    """Fold gives the same text when each space is replaced by a run of spaces, tabs, newlines, carriage
    returns, no-break or ideographic spaces. [M2b]
    Why it matters for a score: a page's line breaks and spacing are not what the tests grade."""
    # Given ordinary text, and the same text with each space replaced by a run of white space
    gap = st.lists(st.sampled_from(" \t\n\u00a0\u3000\r"), min_size=1, max_size=4).map("".join)
    words = s.split(" ")
    spaced = words[0] + "".join(data.draw(gap) + w for w in words[1:])
    # When both are folded; Then they give the same text
    assert fold(spaced) == fold(s)


@relation(HOLDS)
@example("é- a")
@given(PROSE)
def test_fold_ignores_composed_or_decomposed_accents(s):
    """Fold gives the same text for an accent written into its letter or as a separate mark. [M2c]
    Why it matters for a score: a text layer may decompose 'é'; it is still the letter the gold holds."""
    # Given ordinary text with accents; When folded composed (NFC) and decomposed (NFD); Then both agree
    assert fold(unicodedata.normalize("NFD", s)) == fold(unicodedata.normalize("NFC", s))


DASHES = "-‐‑‒–—―−"    # the dash family: hyphens, dashes, minus


@relation(HOLDS)
@example(a="Name", b="5", run="―――", spaced=True)
@given(WORD, WORD, st.text(DASHES, min_size=3, max_size=6), st.booleans())
def test_fold_reads_a_leader_of_any_dash_as_a_space(a, b, run, spaced):
    """Fold reads a run of 3 to 6 characters of the dash family (`-`, `‐`, `‑`, `‒`, `–`, `—`, `―`, `−`, mixed
    or not) between two words, spaced or glued to the first, as one space. [M2f]
    Why it matters for a score: a table of contents or a form may draw its leaders with any dash."""
    # Given two words with a run of dashes between them
    text = f"{a} {run}{' ' * spaced}{b}" if spaced else f"{a}{run} {b}"
    # When folded; Then it reads as the two words with one space
    assert fold(text) == fold(f"{a} {b}"), fold(text)


@relation(HOLDS)
@example(a="Name", b="5", run="。。。")
@given(WORD, WORD, st.text("。｡", min_size=3, max_size=6))
def test_fold_reads_a_leader_of_ideographic_full_stops_as_a_space(a, b, run):
    """Fold reads a run of 3 to 6 ideographic full stops (`。`, `｡`) between two words as one space, as it
    reads a run of dots. [M2g]
    Why it matters for a score: as for M2f, for leaders on a Chinese or Japanese page."""
    # Given two words with a run of ideographic full stops between them
    # When folded; Then it reads as the two words with one space
    assert fold(f"{a} {run} {b}") == fold(f"{a} {b}")


@relation(HOLDS)
@given(PROSE)
def test_the_page_text_ignores_entities(s):
    """A paragraph reads the same whether its `&` and `é` are written literally or as decimal numeric entities
    (`&#38;`, `&#233;`). [M2d]
    Why it matters for a score: '&amp;' and '&' are the same character on the rendered page."""
    # Given ordinary text, and the same text with each `&` and `é` written as a numeric entity
    entities = "".join(f"&#{ord(c)};" if c in "&é" else c for c in s)
    # When each is a paragraph's text, folded; Then both are the same
    assert fold(views.text(f"<p>{s}</p>")) == fold(views.text(f"<p>{entities}</p>"))

# --------------------------------------------------------------------------------------- deletions

EXACT = [t for t in TEXT if t.params.content.max_diffs == 0 and fold(t.params.content.text)]
# Characters a page may drop without changing what a text test compares, by the documented rules of fold
# (docs/scoring/internals.md, Fold), restated here without calling the scorer.
# A run of 3+ dots (… is 3; 。 and ｡ are dots too), dashes, _, = or *.
LEADER = re.compile(r"[.\-\u2026。｡]+|_{3,}|={3,}|\*{3,}")
FOOTNOTE = re.compile(r"\[\^?\d+\]")                        # [12] or [^12]


def why_a_deletion_cannot_count(text: str, i: int) -> str | None:
    """Why deleting text[i] cannot fail a text test, or None: the reasons are fold's documented rules."""
    c = text[i]
    leaders = [m for m in LEADER.finditer(text) if len(m[0]) + 2 * m[0].count("…") >= 3]
    if c.isspace(): return "white space"
    if unicodedata.category(c) in ("Cf", "Co"): return "an invisible or private-use character"
    if any(m.start() <= i < m.end() for m in leaders): return "part of a leader run"
    if c in "•‣◦▪▶∙●" and not text[:i].strip(): return "a bullet opening the text"
    if c in "[]^" and any(m.start() <= i < m.end() for m in FOOTNOTE.finditer(text)):
        return "a bracket of a footnote mark"
    if c in "-‐‑" and 0 < i < len(text) - 1 and text[i - 1].isalpha() and text[i + 1].isspace():
        return "a hyphen at a line end"
    return None


def deletions(t) -> tuple[collections.Counter, list[tuple[int, str]]]:
    """How many deletions of one character were skipped, by reason, and the checked ones that still pass."""
    text, skipped, still_pass = t.params.content.text, collections.Counter(), []
    for i in range(len(text)):
        if why := why_a_deletion_cannot_count(text, i):
            skipped[why] += 1
        elif passes(t.params, f"<p>{escaped(gone := text[:i] + text[i + 1:])}</p>"):
            still_pass.append((i, gone))
    return skipped, still_pass


# Over the real exact text tests: deletions tried, and those skipped by reason (the test below checks both).
REAL_DELETIONS_TRIED = 86_347
REAL_DELETIONS_SKIPPED = {"white space": 12_243, "part of a leader run": 75, "a bullet opening the text": 9,
                          "a bracket of a footnote mark": 6, "a hyphen at a line end": 6,
                          "an invisible or private-use character": 3}
_SKIPPED = sum(REAL_DELETIONS_SKIPPED.values())
SKIPPED_NOTE = (f"{REAL_DELETIONS_TRIED:,} deletions tried; {_SKIPPED:,} skipped ("
                + ", ".join(f"{n:,} {why}" for why, n in REAL_DELETIONS_SKIPPED.items())
                + f"); none of the other {REAL_DELETIONS_TRIED - _SKIPPED:,} passes")


@relation(HOLDS, pool="exact text")
@given(st.sampled_from(EXACT))
def test_deleting_a_character_of_an_exact_text_fails_its_test(t):
    """A text test with no edits allowed passes on its text, and fails on its text with one character deleted,
    for every character except those fold's documented rules make no difference to: white space (fold
    collapses it, and present's retry without spaces removes it), invisible or private-use characters, a
    character of a leader run, a bullet opening the text, a footnote bracket, a line-end hyphen. [M14]
    Why it matters for a score: an exact test must not pass a page that dropped a character."""
    # Given a text test with max_diffs 0; When a page holds its text with one character deleted
    # Then the test fails, unless fold's documented rules drop that character (white space, a leader, ...)
    assert not (bad := deletions(t)[1]), bad[:3]
    # And the text undeleted passes, so the failures are the deletions' doing
    assert passes(t.params, f"<p>{escaped(t.params.content.text)}</p>")


@every_real_test("exact text", note=SKIPPED_NOTE)
def test_every_real_exact_text_fails_with_any_character_deleted():
    """Every real text test with no edits allowed fails with one character deleted, but those skipped. [M14]
    Why it matters for a score: as for M14, over the whole dataset."""
    # Given every real exact text test; When each character is deleted in turn; Then the test fails
    skipped, bad = collections.Counter(), []
    for t in EXACT:
        why, still_pass = deletions(t)
        skipped += why
        bad += [(t.id, i, gone[:60]) for i, gone in still_pass]
    assert not bad, f"{len(bad)} deletions still pass over {len(EXACT)} tests, e.g. {bad[:8]}"
    # And the deletions skipped are the ones the certificate reports
    assert dict(skipped) == REAL_DELETIONS_SKIPPED, dict(skipped)
    assert sum(len(t.params.content.text) for t in EXACT) == REAL_DELETIONS_TRIED

# ------------------------------------------------------------------------------- the case of a page


def with_strings_changed(p, f):
    """The test params `p` with every text string they compare passed through `f`."""
    if isinstance(p, runners.Present):
        return p._replace(content=p.content._replace(text=f(p.content.text)))
    if isinstance(p, runners.Order):
        return p._replace(before=f(p.before), after=f(p.after))
    if isinstance(p, runners.Repeat):
        return p._replace(text=f(p.text))
    return p._replace(cell=f(p.cell), headings=tuple(map(f, p.headings)),
                      section=f(p.section) if p.section else None, row_groups=tuple(map(f, p.row_groups)),
                      relations={k: f(x) for k, x in p.relations.items()})


@relation(HOLDS, pool="text, order, repeat, table_cell")
@given(st.sampled_from([*TEXT, *ORDER, *REPEAT, *CELL]), st.sampled_from([str.upper, str.swapcase]))
def test_a_page_in_another_case_passes_every_text_test(t, change_case):
    """An ASCII text, order, repeat or table_cell test passes on its answer in upper or swapped case, unless a
    string of it has a line-end hyphen (a letter, a hyphen, white space) before a letter, which fold reads by
    case (M2e). M15b's real tests are not ASCII, so outside this promise. [M15a]
    Why it matters for a score: case is folded by every test type, not only by present."""
    # Given an ASCII test with no line-end hyphen (fold reads one by case: M2e)
    strings = text_strings(t.params)
    assume(all(x.isascii() for x in strings))
    assume(not any(LINE_END_HYPHEN_ANY.search(x) for x in strings))
    # When the page holds its answer with the case changed; Then the test passes
    assert passes(t.params, answer_page(with_strings_changed(t.params, change_case)))


@more_evidence()
def test_greek_and_cyrillic_case_folds_like_latin_case():
    """Greek and Cyrillic words fold to the same text as their upper case and title case. [M15a]
    Why it matters for a score: a fold that lowercased only Latin letters would pass M15a and fail here."""
    # Given Greek and Cyrillic words; When folded in lower, upper and title case; Then all are the same
    for word in ("λόγος", "Άγιος", "Привет", "ёж", "ΛΌΓΟΣ".lower()):
        assert fold(word) == fold(word.upper()) == fold(word.title()), word
    # And a text test for a lower-case word passes on the page in capitals
    assert passes(runners.Present(runners.Text("λόγος", 0)), "<p>ΛΌΓΟΣ</p>")
    assert passes(runners.Present(runners.Text("Привет мир", 0)), "<p>ПРИВЕТ МИР</p>")


@relation(INTENDED, domain="4 words: straße, weiß, Bahnhofstraße, ışık")
@deviation("M15b")
@example(word="straße")
@given(st.sampled_from(["straße", "weiß", "Bahnhofstraße", "ışık"]))
def test_a_word_in_upper_case_passes_even_when_upper_case_changes_its_letters(word):
    """A text test for a word whose letters change under upper case passes on the word in upper case: ß and
    dotless ı in the 4 sampled words, and polytonic Greek (ᾳ) in 12 of the 15 real tests that deviate. [M15b]
    Why it matters for a score: 'STRASSE' on a page is the word 'straße' in capitals."""
    # Given a word whose upper case changes its letters; When the page holds it in upper case; Then it passes
    assert passes(runners.Present(runners.Text(word, 0)), f"<p>{word.upper()}</p>")


# The real order and table_cell tests whose gold writes a line-end hyphen in mixed case ('Primary- Revision',
# 'R- Matrix', 'Head- quarters'): fold keeps or joins it by the case each side writes, so the page in another
# case reads it the other way. Present accepts either reading (M11a); order and table_cell do not (M11b).
HYPHEN_BY_CASE = {"23_189451", "p5_PMC12399732.1_t0_head_12_1", *(
    f"p5_PMC1838420.1_t2_head_{x}" for x in ("10_5", "10_8", "12_5", "12_6", "12_7", "12_8", "14_5", "14_6",
                                             "14_7", "14_8", "4_8", "6_8"))}


CASE_NOTE = (f"all except the {len(known_ids('M15b'))} listed under M15b and the {len(HYPHEN_BY_CASE)} "
             "order and table_cell tests whose gold writes a line-end hyphen in mixed case (M11b); upper and "
             "lower case give the same verdict on every real test but those listed under M15b")


@every_real_test("text tests", note=CASE_NOTE)
def test_every_real_text_test_passes_on_its_answer_in_another_case():
    """Every real text test passes on its answer in another case, and gets the same verdict on it in upper
    case as in lower case, except the ones listed. [M15a, M2e, M15b]
    Why it matters for a score: it counts the real tests that M15b touches, and checks M2e over every real
    test."""
    # Given every real text test; When its answer is upper-cased, case-swapped or lower-cased
    tests = [*TEXT, *ORDER, *REPEAT, *CELL]
    upper, swapped, lower = ({t.id for t in tests
                              if passes(t.params, answer_page(with_strings_changed(t.params, f)))}
                             for f in (str.upper, str.swapcase, str.lower))
    # Then upper and lower case give the same verdict (M2e), but on those listed under M15b
    assert not (upper ^ lower) - known_ids("M15b"), sorted((upper ^ lower) - known_ids("M15b"))
    # And those failing in another case are those with a line-end hyphen in mixed case (M11b) and those with a
    # letter whose upper case lowers to other letters (M15b), as known_deviations.json lists them
    failing = {t.id for t in tests} - (upper & swapped)
    strings = {t.id: text_strings(t.params) for t in tests}
    hyphen = {i for i in failing if any(LINE_END_HYPHEN_ANY.search(x) for x in strings[i])}
    assert hyphen == HYPHEN_BY_CASE, {"new": sorted(hyphen - HYPHEN_BY_CASE),
                                      "gone": sorted(HYPHEN_BY_CASE - hyphen)}
    found, known = failing - hyphen, known_ids("M15b")
    assert found == known, ("M15b", {"new": sorted(found - known), "gone": sorted(known - found)})
