"""Relations of text matching: the edit budget (M3, M23), order (M4, M25), repeat (M5), words broken at a
hyphen (M11) and digits glued to an answer (M13)."""
from __future__ import annotations

import random
import string

import pytest
from hypothesis import example, given
from hypothesis import strategies as st

from metamorphic.common import (BUG, CELL, HOLDS, INTENDED, LIMITATION, ORDER, REPEAT, TEXT, answer_page,
                                deviation, escaped, every_real_test, more_evidence, passes, relation)
from omni_parse_bench.normalize import fold
from omni_parse_bench.scorers.unit_tests import runners


def phrase(words):
    return st.lists(st.sampled_from(words), min_size=1, max_size=3).map(" ".join)

# ------------------------------------------------------------------------------------- edit budget


def with_edits(text: str, rnd: random.Random, k: int) -> str:
    """`text` with k random edits: a character replaced by '#', a '#' inserted, or a character deleted."""
    out = list(text)
    for _ in range(min(k, len(out))):
        i = rnd.randrange(len(out))
        match rnd.choice("sid"):
            case "s": out[i] = "#"
            case "i": out.insert(i, "#")
            case _: del out[i]
    return "".join(out)


ANCHOR = "lorem ipsum dolor sit amet"
FIXED = (1, 8, 14)    # the letters M3 edits: none at an end of ANCHOR, none next to another
INNER = [i for i, c in enumerate(ANCHOR) if c != " " and 0 < i < len(ANCHOR) - 1]    # its 22 inner letters
KINDS = ("present", "order", "table_cell")


def edited(mode: str, positions) -> str:
    """ANCHOR with the letters at `positions` replaced by '#' (`sub`), each preceded by an inserted 'z'
    (`insert`), or deleted (`delete`)."""
    return "".join({"sub": "#", "insert": "z" + c, "delete": ""}[mode] if i in positions else c
                   for i, c in enumerate(ANCHOR))


def verdicts(kind: str, written: str, padded: bool = False) -> list[bool]:
    """The verdicts at max_diffs 0..6 of a `kind` test for ANCHOR on a page that writes it as `written`: alone
    in a paragraph (`padded`: between other words, for present), before a paragraph 'tail' (order), or as
    the one cell of a table (table_cell)."""
    pad = "qq vv " if padded else ""
    make, page = {"present": (lambda k: runners.Present(runners.Text(ANCHOR, k)),
                              f"<p>{pad}{written}{pad[::-1]}</p>"),
                  "order": (lambda k: runners.Order(ANCHOR, "tail", k), f"<p>{written}</p><p>tail</p>"),
                  "table_cell": (lambda k: runners.TableCell(ANCHOR, {}, k),
                                 f"<table><tr><td>{written}</td></tr></table>")}[kind]
    return [passes(make(k), page) for k in range(7)]


def needs_exactly(got: list[bool], j: int) -> bool:
    """Whether verdicts at budgets 0..6 fail below j and pass from j on: the budget is j edits, exactly."""
    return not any(got[:j]) and all(got[j:])


@relation(HOLDS, pool="text, order, table_cell")
@given(st.sampled_from([*TEXT, *ORDER, *CELL]), st.integers(0, 3), st.randoms(use_true_random=False))
def test_a_test_that_passes_with_k_edits_allowed_passes_with_more(t, edits, rnd):
    """A text, order or table_cell test that passes with k edits allowed also passes with k + 1, and passes on
    its own answer at its own max_diffs. And on one fixed 26-character text with j = 0 to 3 of its inner
    letters edited, the budget needed is exactly j: for j substitutions in present, order and table_cell; for
    j inserted or j deleted letters in order; for j deleted letters inside a longer line in present (M23a and
    M23b give the edits present and table_cell forgive; M25b gives order pages where a larger budget fails).
    [M3]
    Why it matters for a score: a larger edit budget may only forgive more, never fail a page it passed."""
    # Given a test, and a page holding its answer written `edits` edits off
    p = t.params
    if isinstance(p, runners.Present):
        garbled = p._replace(content=p.content._replace(text=with_edits(p.content.text, rnd, edits)))
    elif isinstance(p, runners.Order):
        garbled = p._replace(before=with_edits(p.before, rnd, edits), after=with_edits(p.after, rnd, edits))
    else:
        garbled = p._replace(cell=with_edits(p.cell, rnd, edits))
    page = answer_page(garbled)
    # When the test is run with max_diffs 0, 1, ..., 6
    def budget(k):
        return p._replace(content=p.content._replace(max_diffs=k)) if isinstance(p, runners.Present) \
            else p._replace(max_diffs=k)
    got = [passes(budget(k), page) for k in range(7)]
    # Then once it passes it keeps passing; with no edit it passes at its own budget (the gold's max_diffs)
    assert got == sorted(got), got
    if edits == 0:
        assert got[p.content.max_diffs if isinstance(p, runners.Present) else p.max_diffs]
    # And on the fixed text j = `edits` edits off, no budget below j passes ("always pass" fails here) and
    # budget j passes (table_cell too: it gets the same float slack as present)
    at = FIXED[:edits]
    exact = [*((k, "sub", False) for k in KINDS), ("order", "insert", False), ("order", "delete", False),
             ("present", "delete", True)]
    for kind, mode, padded in exact:
        assert needs_exactly(got := verdicts(kind, edited(mode, at), padded), edits), (kind, mode, got)


def forgives(kind: str, mode: str, positions, padded: bool) -> None:
    """The budget a `kind` test needs for ANCHOR with the letters at `positions` inserted or deleted is
    exactly their number."""
    got = verdicts(kind, edited(mode, positions), padded)
    assert needs_exactly(got, len(positions)), (edited(mode, positions), got)


EDITS_DOMAIN = ("1-4 of the 22 inner letters of a fixed 26-character text, each deleted or with a 'z' "
                "inserted before it")


@relation(BUG, domain=EDITS_DOMAIN + "; the page holds the text alone or between other words")
@deviation("M23a")
@example(mode="insert", positions={7, 15, 24}, padded=False)
@given(st.sampled_from(["insert", "delete"]), st.sets(st.sampled_from(INNER), min_size=1, max_size=4),
       st.booleans())
def test_present_needs_one_edit_per_inserted_or_deleted_letter(mode, positions, padded):
    """A present test for a fixed 26-character text, on a page with j = 1 to 4 letters inserted into it or
    deleted from it, fails with every budget below j and passes with budget j. [M23a]
    Why it matters for a score: max_diffs says how many edits a page may make; a page that makes more must
    fail."""
    # Given the text with j letters inserted or deleted; When the present test runs with budgets 0..6
    # Then it fails below j and passes from j on
    forgives("present", mode, positions, padded)


@more_evidence()
def test_present_forgives_the_edits_m23a_names():
    """The causes M23a names, pinned. Present passes above its budget on: 3 inserted letters with budget 2; 5
    characters deleted at the end with budget 3; 3 letters substituted in a text that ends or starts the page
    text, with budget 2 (with a word on its other side too, it fails); a letter moved 3 places with budget 1.
    [M23a]
    Why it matters for a score: M23a's test accepts any failure; this check breaks if a cause changes."""
    def verdicts(gold, page):
        return [passes(runners.Present(runners.Text(gold, k)), f"<p>{page}</p>") for k in range(4)]
    # Given a gold, and a page that edits it more than the budget allows
    # When letters are inserted, or deleted at its end; Then a budget below their number passes
    assert verdicts(ANCHOR, "lorem izpsum dolqor sit amjet") == [False, False, True, True]
    assert verdicts(ANCHOR, "lorem ipsum dolor sit")[3]
    # When the text ends or starts the page text, 3 of its letters substituted; Then budget 2 passes
    assert verdicts("lorem ipsum", "abc xxxem ipsum") == [False, False, True, True]
    assert verdicts("lorem ipsum", "lorem ipxxx abc") == [False, False, True, True]
    # And with a word on the other side too, budget 2 fails
    assert verdicts("lorem ipsum", "abc xxxem ipsum dolor") == [False, False, False, True]
    # When a letter moves 3 places (edit distance 2); Then budget 1 passes
    assert verdicts("abcdefgh", "zz acdebfgh zz") == [False, True, True, True]


@relation(INTENDED, domain=EDITS_DOMAIN)
@deviation("M23b")
@example(mode="insert", positions={7, 15, 24})
@given(st.sampled_from(["insert", "delete"]), st.sets(st.sampled_from(INNER), min_size=1, max_size=4))
def test_table_cell_needs_one_edit_per_inserted_or_deleted_letter(mode, positions):
    """A table_cell test for a fixed 26-character cell, on a table whose cell has j = 1 to 4 letters inserted
    or deleted, fails with every budget below j and passes with budget j. [M23b]
    Why it matters for a score: as for M23a, for table cells."""
    # Given the cell with j letters inserted or deleted; When the table_cell test runs with budgets 0..6
    # Then it fails below j and passes from j on
    forgives("table_cell", mode, positions, False)

# ------------------------------------------------------------------------------------------- order

# Short items too: on a page 'x ab', 'x' is two characters before 'ab', which a check with slack would accept.
BEFORE_WORDS, AFTER_WORDS = ["lorem", "ipsum", "dolor", "ab"], ["quis", "vel", "amet", "x"]


@relation(HOLDS)
@example(before="ab", after="x", in_one_paragraph=True)
@given(phrase(BEFORE_WORDS), phrase(AFTER_WORDS), st.booleans())
def test_swapping_two_items_fails_order_but_not_present(before, after, in_one_paragraph):
    """Swapping two texts with no word in common on a page fails the order test of the two and passes the
    present test of each. [M4]
    Why it matters for a score: order grades reading order, and present does not."""
    # Given two texts with no word in common, on one line or in two paragraphs
    page = (lambda a, b: f"<p>{a} {b}</p>") if in_one_paragraph else (lambda a, b: f"<p>{a}</p><p>{b}</p>")
    # When the page holds them in that order, then swapped; Then order(before, after) passes, then fails
    assert passes(runners.Order(before, after, 0), page(before, after))
    assert not passes(runners.Order(before, after, 0), page(after, before))
    # And each text passes present in either order
    for html in (page(before, after), page(after, before)):
        assert passes(runners.Present(runners.Text(before, 0)), html)
        assert passes(runners.Present(runners.Text(after, 0)), html)


@every_real_test("order")
def test_every_real_order_test_fails_on_its_items_swapped():
    """Every real order test fails on a page holding its `after` text before its `before` text. [M4]
    Why it matters for a score: as for M4, over the whole dataset."""
    # Given every real order test; When the page holds `after` then `before`; Then the test fails
    bad = [t.id for t in ORDER
           if passes(t.params, f"<p>{escaped(t.params.after)}</p><p>{escaped(t.params.before)}</p>")]
    assert not bad, f"{len(bad)}/{len(ORDER)} real order tests pass swapped, e.g. {bad[:5]}"


@every_real_test("order")
def test_every_real_order_item_is_present_in_either_order():
    """Both items of every real order test pass a present test on their page, in either order. [M4]
    Why it matters for a score: as for M4, over the whole dataset."""
    # Given every real order test; When the page holds its items in either order; Then each passes present
    bad = []
    for t in ORDER:
        p = t.params
        for page in (f"<p>{escaped(p.before)}</p><p>{escaped(p.after)}</p>",
                     f"<p>{escaped(p.after)}</p><p>{escaped(p.before)}</p>"):
            bad += [(t.id, x[:40]) for x in (p.before, p.after)
                    if not passes(runners.Present(runners.Text(x, p.max_diffs)), page)]
    assert not bad, f"{len(bad)} item/page pairs fail present, e.g. {bad[:5]}"


AB = st.lists(st.text("ab", min_size=1, max_size=3), min_size=1, max_size=2).map(" ".join)


def order_verdicts(before: str, after: str, page: str) -> list[bool]:
    """The verdicts of order(before, after) on a paragraph `page`, at each budget below both items'
    lengths."""
    return [passes(runners.Order(before, after, k), f"<p>{page}</p>")
            for k in range(min(len(fold(before)), len(fold(after))))]


FILLER = st.lists(st.text("ab", min_size=1, max_size=3), max_size=2).map(" ".join)


@relation(HOLDS)
@example(before="a a", after="a a", gaps=("", "", ""))
@given(AB, AB, st.tuples(FILLER, FILLER, FILLER))
def test_an_order_test_that_passes_on_exact_copies_passes_with_any_budget(before, after, gaps):
    """An order test passes, with every budget below its items' lengths, on a page that writes both items
    exactly and in order, with other words around them: short strings of `a`, `b` and spaces, which overlap.
    [M25a]
    Why it matters for a score: an edit to spend may only forgive more; it must not hide an exact copy that
    passes."""
    # Given a page of words that holds `before`, then `after`, written exactly
    x, y, z = gaps
    page = " ".join(filter(None, [x, before, y, after, z]))
    # When the test runs with each budget; Then every verdict passes
    assert all(got := order_verdicts(before, after, page)), (page, got)


@relation(LIMITATION)
@deviation("M25b")
@example(before="aa", after="a ba", page="b b a ab ab")
@given(AB, AB, st.lists(st.text("ab", min_size=1, max_size=3), min_size=1, max_size=5).map(" ".join))
def test_an_order_test_that_passes_with_k_edits_passes_with_more(before, after, page):
    """An order test of short strings of `a`, `b` and spaces that passes with k edits allowed also passes with
    k + 1, on any page of such strings. [M25b]
    Why it matters for a score: as for M3, on items that overlap on the page."""
    # Given two items and a page; When the budget grows; Then once the test passes it keeps passing
    got = order_verdicts(before, after, page)
    assert got == sorted(got), got

# ------------------------------------------------------------------------------------------ repeat


def page_with_lines(text: str, n: int, rnd: random.Random) -> str:
    """A page of n paragraphs holding `text` and three of filler words, shuffled."""
    items = [escaped(text)] * n + [rnd.choice(["foo", "bar", "baz"]) for _ in range(3)]
    rnd.shuffle(items)
    return "".join(f"<p>{x}</p>" for x in items)


@relation(HOLDS)
@given(phrase(["lorem", "ipsum", "dolor", "amet", "sed", "ut", "A7", "x9"]), st.integers(1, 4),
       st.randoms(use_true_random=False))
def test_repeat_needs_exactly_its_count(text, n, rnd):
    """A repeat test of n passes on a page with its text on n lines, and fails with n + 1 or n - 1. [M5]
    Why it matters for a score: repeat is the one test that catches a duplicated or a dropped line."""
    # Given a repeat test of n; When the page holds its text on n lines, among filler lines; Then it passes
    r = runners.Repeat(text, n)
    assert passes(r, page_with_lines(text, n, rnd))
    # When on n + 1 or n - 1 lines; Then it fails
    assert not passes(r, page_with_lines(text, n + 1, rnd))
    assert not passes(r, page_with_lines(text, n - 1, rnd))


@more_evidence(pool="repeat")
@given(st.sampled_from(REPEAT), st.randoms(use_true_random=False))
def test_repeat_needs_exactly_its_count_on_loaded_tests(t, rnd):
    """The same holds for each loaded repeat test and its own text and count. [M5]
    Why it matters for a score: as for M5, on the texts the tests really hold."""
    # Given a loaded repeat test; When its text is on exactly its count of lines, or one more or fewer
    # Then it passes, then fails twice
    p = t.params
    assert passes(p, page_with_lines(p.text, p.expected_count, rnd))
    assert not passes(p, page_with_lines(p.text, p.expected_count + 1, rnd))
    assert not passes(p, page_with_lines(p.text, p.expected_count - 1, rnd))

# ------------------------------------------------------------------------- a word broken at a hyphen

LOWER = st.text(string.ascii_lowercase, min_size=2, max_size=6)
GLUE = st.sampled_from(["<br>", " ", "\n", "<br> "])


def broken_word_check(kind: str, left: str, right: str, glue: str):
    """The test of kind `kind` for 'left-right', and the page holding the word broken after its hyphen by
    `glue`."""
    word, broken = f"{left}-{right}", f"{left}-{glue}{right}"
    return {"present": (runners.Present(runners.Text(word, 0)), f"<p>{broken}</p>"),
            "order": (runners.Order(word, "tail", 0), f"<p>{broken}</p><p>tail</p>"),
            "repeat": (runners.Repeat(word, 1), f"<p>{broken}</p>"),
            "table_cell": (runners.TableCell(word, {}, 0), f"<table><tr><td>{broken}</td></tr></table>"),
            }[kind]


@relation(HOLDS)
@example(left="aa", right="bb", glue="<br>")
@example(left="aa", right="bb", glue=" ")
@given(LOWER, LOWER, GLUE)
def test_present_finds_a_hyphenated_word_broken_at_its_hyphen(left, right, glue):
    """A present test for a hyphenated word of two lowercase ASCII parts of 2-6 letters passes on a page that
    breaks it after its hyphen (with `<br>`, a space or a newline). [M11a]
    Why it matters for a score: a line break inside 'self-aware' is layout, not a misread word."""
    # Given a test for 'left-right'; When the page holds it whole, then broken after the hyphen
    # Then both pass
    for g in ("", glue):
        params, page = broken_word_check("present", left, right, g)
        assert passes(params, page), page


@relation(INTENDED)
@deviation("M11b")
@pytest.mark.parametrize("kind", ["order", "repeat", "table_cell"])
@example(left="aa", right="bb", glue="<br>")
@example(left="aa", right="bb", glue=" ")
@given(LOWER, LOWER, GLUE)
def test_other_text_tests_find_a_hyphenated_word_broken_at_its_hyphen(kind, left, right, glue):
    """Order, repeat and table_cell tests for a hyphenated word pass when it breaks after the hyphen. [M11b]
    Why it matters for a score: as for M11a, for the test types other than present."""
    # Given a test for 'left-right'; When the page holds it whole, then broken after the hyphen
    # Then both pass
    for g in ("", glue):
        params, page = broken_word_check(kind, left, right, g)
        assert passes(params, page), page

# -------------------------------------------------------------------- a digit glued to an answer


def digit_glued(text: str, d: str) -> list[str]:
    """`text` with the digit d glued before it if it starts with a digit, and after it if it ends with one."""
    s = text.strip()
    return [*([d + s] if s[0].isdigit() else []), *([s + d] if s[-1].isdigit() else [])]


def glued_pages(p, d: str) -> list[str]:
    """Pages holding the answer of a text, order or repeat test with the digit d glued to a digit end."""
    if isinstance(p, runners.Present):
        return [f"<p>{escaped(g)}</p>" for g in digit_glued(p.content.text, d)]
    if isinstance(p, runners.Order):
        return [*(f"<p>{escaped(g)}</p><p>{escaped(p.after)}</p>" for g in digit_glued(p.before, d)),
                *(f"<p>{escaped(p.before)}</p><p>{escaped(g)}</p>" for g in digit_glued(p.after, d))]
    return ["".join(f"<p>{escaped(g)}</p>" for _ in range(p.expected_count)) for g in digit_glued(p.text, d)]


def digit_edged(tests):
    """The tests with an ASCII string that starts or ends with a digit."""
    def edged(p):
        strings = [p.content.text] if isinstance(p, runners.Present) else \
            [p.before, p.after] if isinstance(p, runners.Order) else [p.text]
        return any((x := s.strip()) and x.isascii() and (x[0].isdigit() or x[-1].isdigit()) for s in strings)
    return [t for t in tests if edged(t.params)]


DIGIT_EDGED = {"present": digit_edged(TEXT), "order": digit_edged(ORDER), "repeat": digit_edged(REPEAT)}


@relation(HOLDS)
@given(st.integers(1, 99999), st.integers(0, 2), st.booleans(), st.sampled_from("0123456789"))
def test_a_digit_glued_to_a_text_that_ends_in_a_digit_fails_present(n, k, front, d):
    """A text test whose ASCII text starts or ends with a number fails with an ASCII digit glued to that
    number, with 0 to 2 edits allowed (real tests: their own max_diffs). [M13a]
    Why it matters for a score: '2019' must not pass on '20190', even with edits allowed."""
    # Given a text test for '{n} alpha' or 'alpha {n}' with 0 to 2 edits allowed: it passes on its text
    text = f"{n} alpha" if front else f"alpha {n}"
    p = runners.Present(runners.Text(text, k))
    assert passes(p, f"<p>{text}</p>")
    # When a digit is glued to the number, in the same word; Then it fails
    assert not passes(p, f"<p>{d + text if front else text + d}</p>")


@relation(HOLDS)
@given(st.integers(1, 99999), st.integers(1, 3), st.booleans(), st.sampled_from("0123456789"))
def test_a_digit_glued_to_a_line_that_ends_in_a_digit_fails_repeat(n, count, front, d):
    """A repeat test whose ASCII line starts or ends with a number fails with an ASCII digit glued to that
    number. [M13b]
    Why it matters for a score: as for M13a, for repeat."""
    # Given a repeat test of '{n} alpha' or 'alpha {n}': it passes on its lines
    text = f"{n} alpha" if front else f"alpha {n}"
    glued = d + text if front else text + d
    assert passes(runners.Repeat(text, count), "".join(f"<p>{text}</p>" for _ in range(count)))
    # When a digit is glued to each line's number; Then it fails
    assert not passes(runners.Repeat(text, count), "".join(f"<p>{glued}</p>" for _ in range(count)))


@more_evidence(pool="digit-edged text, repeat",
               case_of={"M13a": {"kind": "present"}, "M13b": {"kind": "repeat"}})
@pytest.mark.parametrize("kind", ["present", "repeat"])
@given(d=st.sampled_from("0123456789"), data=st.data())
def test_a_digit_glued_to_a_loaded_digit_edged_test_fails_it(kind, d, data):
    """The same holds for each loaded text and repeat test whose ASCII string starts or ends with a digit, at
    its own max_diffs. [M13a, M13b]
    Why it matters for a score: as for M13a, on the texts the tests really hold."""
    if not DIGIT_EDGED[kind]:
        pytest.skip(f"no digit-edged {kind} test is loaded")
    # Given a loaded test whose text has a digit at an end; When a digit is glued there; Then it fails
    t = data.draw(st.sampled_from(DIGIT_EDGED[kind]))
    assert not any(passes(t.params, page) for page in glued_pages(t.params, d))


@relation(HOLDS, domain="drawn from 320 combinations (n 1-8, digit 0-9, front or back, which item), so CI "
                        "may not run every one")
@example(n=1, d="1", front=True, glue_before=True)
@given(st.integers(1, 8), st.sampled_from("0123456789"), st.booleans(), st.booleans())
def test_a_digit_glued_to_an_order_item_that_ends_in_a_digit_fails_order(n, d, front, glue_before):
    """An order test whose ASCII items start or end with a number passes on its items, and fails with an
    ASCII digit glued to either number. [M13c]
    Why it matters for a score: item '1.' must not be found in '11.'; the same for items that end in a
    digit."""
    # Given an order test of two numbered items
    before, after = (f"{n}. alpha", f"{n + 1}. beta") if front else (f"alpha {n}", f"beta {n + 1}")
    assert passes(runners.Order(before, after, 0), f"<p>{before}</p><p>{after}</p>")
    # When a digit is glued to the number of one item, in the same word; Then it fails
    glued = (lambda x: d + x) if front else (lambda x: x + d)
    page = f"<p>{glued(before)}</p><p>{after}</p>" if glue_before else f"<p>{before}</p><p>{glued(after)}</p>"
    assert not passes(runners.Order(before, after, 0), page)


@every_real_test({"M13a": "digit-edged text", "M13b": "digit-edged repeat", "M13c": "digit-edged order"})
@pytest.mark.parametrize("kind", ["present", "repeat", "order"])
def test_every_real_digit_edged_test_fails_with_a_digit_glued(kind):
    """Every real text, repeat or order test whose ASCII string starts or ends with a digit fails, at its own
    max_diffs, with any ASCII digit glued to that end. [M13a, M13b, M13c]
    Why it matters for a score: as for M13a to M13c, over the whole dataset."""
    # Given every real test with a digit at an end; When each digit 0-9 is glued there; Then it fails
    tests = DIGIT_EDGED[kind]
    assert tests, f"no digit-edged {kind} tests in the dataset"
    bad = [(t.id, page[:60]) for t in tests for d in "0123456789" for page in glued_pages(t.params, d)
           if passes(t.params, page)]
    assert not bad, f"{kind}: {len(bad)} glued digits still pass over {len(tests)} tests, e.g. {bad[:6]}"


@relation(HOLDS)
@example(left="self", right="aware", n=40, d="0", front=False)
@given(LOWER, LOWER, st.integers(1, 999), st.sampled_from("0123456789"), st.booleans())
def test_a_digit_glued_to_a_number_fails_present_when_a_word_breaks_at_its_hyphen(left, right, n, d, front):
    """A text test with no edits allowed for a hyphenated word and a number (`self-aware 40`, `40 self-aware`)
    passes on a page that breaks the word after its hyphen, and fails there with an ASCII digit glued to the
    number. [M13d]
    Why it matters for a score: the hyphen fallback must judge the number's edge as the main match does; '40'
    must not pass on '400'."""
    # Given a text test for a hyphenated word and a number, and the page with the word broken at its hyphen
    word, broken = f"{left}-{right}", f"{left}- {right}"
    text, page, glued = ((f"{n} {word}", f"{n} {broken}", f"{d}{n} {broken}") if front else
                         (f"{word} {n}", f"{broken} {n}", f"{broken} {n}{d}"))
    p = runners.Present(runners.Text(text, 0))
    # When the number is as written; Then it passes. When a digit is glued to it; Then it fails
    assert passes(p, f"<p>{page}</p>")
    assert not passes(p, f"<p>{glued}</p>")


@relation(HOLDS)
@example(word="Total", n=40, d="0", k=1, glued_first=True)
@given(st.sampled_from(["Total", "Fee", "Item no", "x"]), st.integers(10, 999), st.sampled_from("0123456789"),
       st.integers(1, 2), st.booleans())
def test_a_copy_with_a_digit_glued_does_not_veto_a_match_elsewhere(word, n, d, k, glued_first):
    """A text test with 1 or 2 edits allowed (`Total: 40`) that passes on a paragraph one digit off
    (`Total: 41`) still passes when another paragraph holds its text with a digit glued (`Total: 400`), before
    or after it. [M13e]
    Why it matters for a score: one acceptable copy anywhere on the page is enough; a rejected copy elsewhere
    must not cancel it."""
    # Given a text test with an edit to spend, and a paragraph one digit off that passes it
    text = f"{word}: {n}"
    near = f"{word}: {n - n % 10 + (n + 1) % 10}"
    p = runners.Present(runners.Text(text, k))
    assert passes(p, f"<p>{near}</p>")
    # When a paragraph holds the text with a digit glued, before or after; Then it still passes
    glued = f"<p>{text}{d}</p>"
    assert passes(p, glued + f"<p>{near}</p>" if glued_first else f"<p>{near}</p>" + glued)
