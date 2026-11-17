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
                                deviation, escaped, every_real_test, exact_case_tests, known_ids,
                                more_evidence, passes,
                                relation, text_strings)
from omni_parse_bench import views
from omni_parse_bench.normalize import fold, fold_cased
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


CASE_NOTE = (f"all except the {len(known_ids('M15b'))} listed under M15b; upper and lower case give the same "
             "verdict on every real test but those")


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
    # Then upper and lower case give the same verdict (M2e, M15b), but on those listed under M15b
    assert not (upper ^ lower) - known_ids("M15b"), sorted((upper ^ lower) - known_ids("M15b"))
    # And those failing in another case are those with the letters of M15b, as known_deviations.json lists
    # them; none is left over (M15b), a line-end hyphen in mixed case included: present, order, repeat and
    # table_cell read such a hyphen kept or dropped (M11a, M11b)
    failing = {t.id for t in tests} - (upper & swapped)
    assert failing == known_ids("M15b"), {"new": sorted(failing - known_ids("M15b")),
                                          "gone": sorted(known_ids("M15b") - failing)}


# ------------------------------------------------------------------------ exact_case: the case kept


def exact(text: str, edits: int = 0) -> runners.Present:
    """A present test of `text` whose arg sets `exact_case`."""
    return runners.Present(runners.Text(text, edits, (), True))


def flipped(s: str, i: int) -> str:
    """`s` with the case of its letter number `i` (counting only cased single-character letters) swapped."""
    spots = [k for k, c in enumerate(s) if c.swapcase() != c and len(c.swapcase()) == 1
             and c.swapcase().swapcase() == c]
    k = spots[i % len(spots)]
    return s[:k] + s[k].swapcase() + s[k + 1:]


def has_cased_letter(s: str) -> bool:
    return any(c.swapcase() != c and len(c.swapcase()) == 1 and c.swapcase().swapcase() == c for c in s)


@relation(HOLDS, domain="words (ASCII letters, digits and éüñàçöå), '&' words and the marks . , - (x) 50% "
                        "1,000, in the case written; the loaded exact_case tests")
@given(PROSE)
def test_a_text_passes_on_its_own_case_with_exact_case(s):
    """A text test whose arg sets exact_case passes on a page that writes its text in the case it has, for
    words, '&' words and the marks . , - (x) 50% 1,000, and for every loaded test that sets exact_case. [M29]
    Why it matters for a score: exact_case must keep every correct page, in any case the gold has (`iPhone`,
    `NASA`, a German noun), or it would punish what it is meant to protect."""
    # Given a text a gold file may hold (something is left of it after folding), with no line-end hyphen
    # (whose reading depends on case: M2e)
    assume(fold(s) and not LINE_END_HYPHEN.search(s))
    # When a page writes it as it is and a test of it sets exact_case; Then the test passes
    assert passes(exact(s), f"<p>{escaped(s)}</p>", exact=True)
    # And so does every loaded test that sets exact_case, on its own answer
    for t in exact_case_tests():
        assert passes(t.params, answer_page(t.params), exact=True), t.id


@relation(HOLDS, domain="words (ASCII letters, digits and éüñàçöå), '&' words and the marks . , - (x) 50% "
                        "1,000, with one letter's case swapped")
@given(PROSE, st.integers(0, 500))
def test_swapping_the_case_of_one_letter_fails_exact_case_and_passes_without_it(s, i):
    """A text test passes on a page that writes its text with the case of one letter swapped when the arg does
    not set exact_case (M2a, M15a), and fails on it when the arg sets exact_case, for text with a cased letter
    and no line-end hyphen. [M30]
    Why it matters for a score: `NASA` for `Nasa`, `Co` for `CO` or `iPhone` for `iphone` is the error
    exact_case is for; the setting must not be a no-op."""
    # Given a text with a cased letter and no line-end hyphen (whose reading depends on case: M2e)
    assume(has_cased_letter(s) and fold(s) and not LINE_END_HYPHEN.search(s))
    # When a page writes it with the case of one letter swapped
    page = f"<p>{escaped(flipped(s, i))}</p>"
    # Then a test without exact_case passes, and the same test with exact_case fails
    assert passes(runners.Present(runners.Text(s, 0)), page)
    assert not passes(exact(s), page, exact=True)


CASE_FLIP_NOTE = ("the first cased letter of every real text string swapped: exact_case fails on each")


@every_real_test("text strings", note=CASE_FLIP_NOTE)
def test_every_real_text_string_fails_with_one_letter_case_swapped_under_exact_case():
    """Every real text string, were it the text of an arg that sets exact_case, fails with its first cased
    letter swapped, and passes in its own case, but those with a checkbox ([x]: fold reads [x] and [X] as one
    checked box). [M30, M29]
    Why it matters for a score: it checks the setting on real strings: a hyphen, a footnote or a squeeze path
    that lowercased would let a wrong-case page through on some of them."""
    # Given every text string of every real test; When it is the text of an arg that sets exact_case
    bad_flip, bad_own = [], []
    for t in TESTS:
        for n, text in enumerate(text_strings(t.params)):
            # Note: a checkbox "[x]" or "[X]" is one checked box (a mark, not a letter): no case
            if not has_cased_letter(text) or re.search(r"\[[xX]\]", text):
                continue
            e = exact(text)
            # Then it passes on its answer, and fails with a letter's case swapped
            if not passes(e, answer_page(e), exact=True):
                bad_own.append(f"{t.id}#{n}")
            if passes(e, f"<p>{escaped(flipped(text, 0))}</p>", exact=True):
                bad_flip.append(f"{t.id}#{n}")
    assert not bad_own and not bad_flip, {"own": bad_own[:5], "flip": bad_flip[:5]}


SPACES = st.lists(st.sampled_from(" \t\n\u00a0\u3000\r"), min_size=1, max_size=4).map("".join)


@relation(HOLDS, domain="words (ASCII letters, digits and éüñàçöå), '&' words and the marks . , - (x) 50% "
                        "1,000: runs of white space, entities, NFD, and the answer in <b> <i> <span> <em> "
                        "<strong> <u> <small> <a>")
@given(PROSE, st.data(), st.sampled_from(["b", "i", "span", "em", "strong", "u", "small", "a"]))
def test_exact_case_still_ignores_spacing_entities_accents_and_markup(s, data, tag):
    """A text test whose arg sets exact_case passes on its text with each space replaced by a run of white
    space, with its characters written as entities, with its accents decomposed (NFD), and with a head, a
    tail or all of it in an inline tag. [M31]
    Why it matters for a score: exact_case keeps case only; spacing, entities, accents and styling are as
    ungraded as without it (M2b, M2c, M7a)."""
    # Given a text a gold file may hold (something is left after folding), with no line-end hyphen (M2e)
    assume(fold(s) and not LINE_END_HYPHEN.search(s))
    words = s.split(" ")
    spaced = words[0] + "".join(data.draw(SPACES) + w for w in words[1:])
    cut = data.draw(st.integers(0, len(s)))
    a, b = escaped(s[:cut]), escaped(s[cut:])
    pages = [f"<p>{escaped(spaced)}</p>",                                                      # spacing
             f"<p>{''.join(f'&#{ord(c)};' if c != ' ' else c for c in s)}</p>",               # entities
             f"<p>{escaped(unicodedata.normalize('NFD', s))}</p>",                              # accents
             f"<p><{tag}>{a}</{tag}>{b}</p>", f"<p>{a}<{tag}>{b}</{tag}></p>",                  # markup
             f"<p><{tag}>{escaped(s)}</{tag}></p>"]
    # When each page is scored with an exact_case test of s; Then each passes
    assert [passes(exact(s), page, exact=True) for page in pages] == [True] * len(pages)


@more_evidence()
def test_exact_case_still_folds_quotes_dashes_glyphs_and_wrapped_lines():
    """A text test whose arg sets exact_case passes on its text with quotes, dashes, a ligature, full-width
    letters or a footnote mark written another way, and with a word broken at a line end, in the case the gold
    has; and fails when one letter of it has another case. [M31]
    Why it matters for a score: as for M31, for the folds that are not about spacing or markup."""
    # Given texts, and pages that write them another way but in the same case
    cases = [("\u201cNASA\u201d said it\u2019s \u2018Okay\u2019", "<p>\"NASA\" said it's 'Okay'</p>"),
             ("Pre-post Test", "<p>Pre\u2013post Test</p>"), ("Pre-post Test", "<p>Pre\u2212post Test</p>"),
             ("figure One", "<p>\ufb01gure One</p>"),
             ("iPhone Pro", "<p>\uff49\uff30hone Pro</p>"),
             ("Smith and Jones", "<p>Smith<sup>1</sup> and Jones</p>"),
             ("Smith and Jones", "<p>Smith[1] and Jones</p>"), ("Headquarters", "<p>Head-\nquarters</p>"),
             ("Headquarters", "<p>Head- quarters</p>"), ("Total due", "<p>Total ........ due</p>")]
    for text, page in cases:
        # Then the test passes
        assert passes(exact(text), page, exact=True), (text, page)
    # And a page with one letter in another case fails
    for text, page in [("NASA said", "<p>Nasa said</p>"),
                       ("Smith and Jones", "<p>smith<sup>1</sup> and Jones</p>"),
                       ("Headquarters", "<p>head-\nquarters</p>"),
                       ("Head quarters", "<p>head-\nquarters</p>"),
                       ("Pre-post Test", "<p>Pre\u2013post test</p>")]:
        assert not passes(exact(text), page, exact=True), (text, page)


@relation(HOLDS, domain="strings of ASCII letters, digits, accents é ü, a few symbols (& . , %), quotes and "
                        "spaces; no hyphen, dash, bracket or bullet (those are M1a, M1b, M1c, M1e)")
@example("A'\u2019B")
@given(st.text(string.ascii_letters + string.digits + "éÉüÜ&.,% '\u2018\u2019`\"\u201c\u201d"))
def test_folding_with_case_kept_twice_is_folding_it_once(s):
    """`fold_cased` twice gives the same text as once, for strings of letters in both cases, digits, accents,
    '& . , %', quotes and spaces. [M32]
    Why it matters for a score: exact_case compares the gold and the page each folded once; a second fold
    that changed the text would show the case-kept form is not final (as M1d for `fold`)."""
    # Given a string s with both cases; When it is folded once and twice, with case kept; Then both agree
    assert fold_cased(fold_cased(s)) == fold_cased(s)
    # And fold_cased is fold without lowercasing: lowercasing it gives fold's text
    assert fold_cased(s).lower() == fold(s)


@relation(HOLDS, domain="130 words broken after 2-5 letters (the second part in lower case), the first part "
                        "in lower, Capitalized or UPPER case; one letter's case swapped")
@given(st.text(string.ascii_lowercase, min_size=2, max_size=5), st.text(string.ascii_lowercase, min_size=2,
                                                                         max_size=5),
       st.sampled_from([str.lower, str.capitalize, str.upper]), st.sampled_from([" ", "\n", "  \n "]),
       st.integers(0, 500))
def test_a_word_broken_at_a_line_end_keeps_its_case_under_exact_case(first, rest, style, gap, i):
    """A text test for a word, whose arg sets exact_case, passes on the page that breaks it after a hyphen at
    a line end when the page has the word's case, and fails when one letter has another case; without
    exact_case both pass (the hyphen is read kept or dropped, M11a). The letter swapped is not the first
    of the second part (a capital there is read as a compound hyphen: M2e). [M33]
    Why it matters for a score: the hyphen fallback re-reads the page's text; if it lowercased, `Develop- ers`
    and `develop- ers` would both pass an exact_case test of `Developers`."""
    word = style(first) + rest
    broken = f"{style(first)}-{gap}{rest}"
    # Given a word of the case `style`, and a page that breaks it at a line end with a hyphen
    assert passes(exact(word), f"<p>{broken}</p>", exact=True)
    # When one letter of the word, not the first of its second part, has the other case on the page
    where = i % (len(first) + len(rest) - 1)
    where = where if where < len(first) else where + 1
    letters = list(broken)
    spots = [k for k, c in enumerate(broken) if c.isalpha()]
    k = spots[where]
    letters[k] = letters[k].swapcase()
    page = f"<p>{''.join(letters)}</p>"
    # Then the exact_case test fails, and the test without exact_case still passes
    assert not passes(exact(word), page, exact=True), page
    assert passes(runners.Present(runners.Text(word, 0)), page), page
