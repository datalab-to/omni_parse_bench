# ruff: noqa: E501
"""Relations of the normalizer chain and its distance (M205 to M216): the gold written as the output passes; what the
chain frees changes no verdict; a quantity is atomic; a budget only widens; a match stops at a token edge; copies change
nothing for an exists test; the whole-mode relation is symmetric at Text; raw candidates only grow along the chain;
Hangul spacing is free; a glued unit keeps its case. The loaded strings are the gold's own, matched with `chain` on."""
from __future__ import annotations

import re

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, every_real_test, relation, text_strings
from omni_parse_bench import chain, reader, switches

RESERVED = re.compile("[\\ufdd0-\\ufdd2\\u2029\\n\\r<>&]")
STRINGS = sorted({x for t in TESTS for x in text_strings(t.params) if x.strip() and not RESERVED.search(x)})
MULTI = [x for x in STRINGS if len(x.split()) >= 2]
HANGUL = [x for x in STRINGS if re.search("[가-힣]{2}", x)] + ["서울대학교 입학 안내", "한국어 문장 예시"]
QTYS = [x for x in STRINGS if any(c.isdigit() for c in x)] + ["Revenue 1M", "Weight 5kg", "3万 yen", "Distance 10km", "Heap 4GB"]


UNITS = [x for x in QTYS if re.search(r"\d[A-Za-z]+\b", x)] + ["Revenue 1M", "Weight 5kg", "Distance 10km", "Heap 4GB"]
LATIN_END = [x for x in STRINGS if re.search(r"(?<![\w-])[A-Za-z]{2,}$", x)] + ["the Total", "Total"]
LOOSE = settings(suppress_health_check=[HealthCheck.filter_too_much, HealthCheck.too_slow, HealthCheck.data_too_large])


def page(x: str) -> str:
    return f"<p>{escaped(x)}</p>"


def found(gold: str, html: str, point: str = chain.WORDS, k: int = 0, rules=None) -> bool:
    with switches.set_all(True):
        return chain.match(chain.tokens_of_gold(gold), chain.tokens_of_output(html), point, k, rules=rules)


def cands(gold: str, html: str, point: str, k: int = 0) -> set[tuple[int, int]]:
    with switches.set_all(True):
        return {(w.first, w.last) for w in chain.windows(chain.tokens_of_gold(gold), chain.tokens_of_output(html), point, k)}


@relation(HOLDS, domain="every loaded text string x 3 points (Text, Cased, Words) x the string written as a paragraph",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.sampled_from([chain.TEXT, chain.CASED, chain.WORDS]))
def test_the_gold_written_as_the_output_passes(x, point):
    """A text claim written out as the page's only paragraph is found, at every point of the chain, with no budget. [M205]
    Why it matters for a score: the trivial output of a positive text test passes, so the chain cannot fail a faithful
    transcription on its own reading rules."""
    assert found(x, page(x), point), (x, point)


@relation(HOLDS, domain="every loaded string of two or more words x 4 rewrites of the page (a footnote mark after the "
                        "first word, the gold's space dropped, a space as a line break, a space as a block break)",
          pool="text, order, repeat, table_cell")
@LOOSE
@given(st.sampled_from(MULTI), st.integers(0, 3))
def test_what_the_chain_frees_changes_no_verdict(x, how):
    """From Cased on, a footnote mark inserted after a word, a space the gold has dropped from the output, a space written
    as a `<br>` or as a block break, leaves a passing text claim passing. [M206]
    Why it matters for a score: a system that sets a footnote, glues two words or breaks a line differently from the gold
    is not marked wrong for it."""
    assume(x == x.strip())
    with switches.set_all(True):
        assume(reader.tokenize(x)[0].cls == "Word")        # a leading quantity is atomic: `16S` is not `16SrDNA`
    words = x.split()
    assume(all(w[-1:].isalpha() for w in words[:1]) and len(words[0]) > 1)
    assume(found(x, page(x)))
    first, rest = words[0], x[len(words[0]):].lstrip()
    assume(rest and not re.match(r"[\d\-+±.,'$€£¥%]", rest))
    html = [f"<p>{escaped(first)}<sup>1</sup> {escaped(rest)}</p>", f"<p>{escaped(first)}{escaped(rest)}</p>",
            f"<p>{escaped(first)}<br>{escaped(rest)}</p>", f"<p>{escaped(first)}</p><p>{escaped(rest)}</p>"][how]
    assert found(x, html), (x, html)


@relation(HOLDS, domain="every loaded string with a digit x one digit of one quantity changed x a budget of 0 to 3",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(QTYS), st.data(), st.integers(0, 3))
def test_changing_one_digit_of_a_quantity_fails_at_any_budget(x, data, k):
    """In an output whose only reading of the claim is the claim itself, changing one digit of one of its quantities makes
    the claim fail, at every budget. [M207]
    Why it matters for a score: a quantity is atomic, so a budget never pays for a wrong number."""
    with switches.set_all(True):
        toks = reader.tokenize(x)
    qs = [t for t in toks if t.cls == "Qty" and any(c.isdigit() for c in t.text)]
    assume(qs)
    q = data.draw(st.sampled_from(qs))
    digits = [i for i, c in enumerate(q.text) if c in "0123456789"]
    assume(digits)
    i = data.draw(st.sampled_from(digits))
    new = str((int(q.text[i]) + data.draw(st.integers(1, 9))) % 10)
    changed = x[: q.start] + q.text[:i] + new + q.text[i + 1:] + x[q.end:]
    assume(q.end <= len(x) and x[q.start:q.end] == q.text)
    assume(len([t for t in toks if t.cls == "Qty"]) == 1 and len(toks) <= 12)
    assert not found(x, page(changed), chain.WORDS, k), (x, changed, k)


@relation(HOLDS, domain="every loaded text string x a budget of 0 to 2 x a typo (a swap of two letters)",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.integers(0, 2), st.data())
def test_a_budget_only_widens(x, k, data):
    """A claim that passes at a budget passes at the next; a swap of two neighbouring letters of a word is one edit
    (OSA). [M208]
    Why it matters for a score: raising `max_diffs` never fails a test that passed, and one transposed pair costs one."""
    out = page(x)
    if found(x, out, chain.WORDS, k):
        assert found(x, out, chain.WORDS, k + 1)
    letters = [i for i in range(len(x) - 1) if x[i].isalpha() and x[i + 1].isalpha() and x[i] != x[i + 1] and x[i].islower() == x[i + 1].islower() and x[i].isascii() and x[i + 1].isascii()]
    assume(letters)
    i = data.draw(st.sampled_from(letters))
    swapped = x[:i] + x[i + 1] + x[i] + x[i + 2:]
    assume(len(chain.tokens_of_gold(x)) == len(chain.tokens_of_gold(swapped)))
    assume(chain.tokens_of_gold(x)[0].cls != "Qty" or " " in x)
    assert found(x, page(swapped), chain.WORDS, 1), (x, swapped)


@relation(HOLDS, domain="every loaded text string whose last token is a Latin word x a letter appended to it",
          pool="text, order, repeat, table_cell")
@LOOSE
@given(st.sampled_from(LATIN_END))
def test_a_match_stops_at_a_token_edge(x):
    """Appending a letter to a word that ends the only reading of the claim makes the claim fail. [M209]
    Why it matters for a score: `Total` is not found in `Totally`, nor `cat` in `concatenate`."""
    with switches.set_all(True):
        toks = [t for t in reader.tokenize(x) if t.cls not in ("Space", "Break")]
    assume(toks and toks[-1].cls == "Word" and toks[-1].script == "" and toks[-1].text.isascii() and toks[-1].text.isalpha())
    assume(x.endswith(toks[-1].text))
    assert not found(x, page(x + "y")), x


@relation(HOLDS, domain="every loaded text string x the output with the claim written twice, or once corrupted and once whole",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.booleans())
def test_copies_change_no_exists_verdict(x, corrupt):
    """For a text claim, writing the claim twice, or corrupting one copy while another stands, leaves it passing. [M210]
    Why it matters for a score: a page that repeats a line, or has one misread copy, still holds the line."""
    assume(len(x) > 4)
    bad = escaped(x[:2] + "#" + x[3:])
    html = f"<p>{bad}</p><p>{escaped(x)}</p>" if corrupt else f"<p>{escaped(x)}</p><p>{escaped(x)}</p>"
    assert found(x, html), (x, html)


@relation(HOLDS, domain="every loaded text string x a typo in it (one letter replaced)",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.data())
def test_the_whole_relation_is_symmetric_at_text(x, data):
    """At Text, whether a string as a whole is within a budget of another does not depend on which one is the gold. [M211]
    Why it matters for a score: the distance does not favour one side of a comparison."""
    assume(len(x) > 2)
    i = data.draw(st.integers(0, len(x) - 1))
    y = x[:i] + "q" + x[i + 1:]
    with switches.set_all(True):
        a, b = chain.tokens_of_gold(x), chain.tokens_of_gold(y)
        for k in (0, 1, 2):
            assert chain.equal(a, b, chain.TEXT, k) == chain.equal(b, a, chain.TEXT, k), (x, y, k)


@relation(HOLDS, domain="every loaded text string x 3 outputs (the string, in capitals, with a footnote mark and an extra space)",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(STRINGS), st.integers(0, 2))
def test_raw_candidates_only_grow_along_the_chain(x, how):
    """The windows that match at Text match at Cased, and those at Cased match at Words, for the same output. [M212]
    Why it matters for a score: a coarser reading adds passes for an exists test, never takes one away."""
    html = [page(x), page(x.upper()), f"<p>{escaped(x)}<sup>1</sup> {escaped(x)}</p>"][how]
    text, cased, words = (cands(x, html, p) for p in (chain.TEXT, chain.CASED, chain.WORDS))
    assert text <= cased <= words, (x, how)


@relation(HOLDS, domain="every loaded string with two Hangul syllables x a space added or removed between two of them",
          pool="text, order, repeat, table_cell")
@given(st.sampled_from(HANGUL), st.data())
def test_hangul_spacing_changes_no_raw_candidate_from_cased_on(x, data):
    """Adding or removing a space between two Hangul syllables of the output leaves the raw candidates at Cased and at
    Words as they were. [M213]
    Why it matters for a score: Korean outputs that space differently from the gold are not marked wrong."""
    pairs = [m.start() + 1 for m in re.finditer("[가-힣](?=[가-힣])", x)]
    assume(pairs)
    i = data.draw(st.sampled_from(pairs))
    spaced = x[:i] + " " + x[i:]
    for p in (chain.CASED, chain.WORDS):
        assert found(x, page(spaced), p) == found(x, page(x), p), (x, p)
        assert found(spaced, page(x), p) == found(x, page(x), p), (x, p)


@relation(HOLDS, domain="every loaded string with a quantity that has a glued unit or magnitude in capitals or lower case x its case swapped",
          pool="text, order, repeat, table_cell")
@LOOSE
@given(st.sampled_from(UNITS))
def test_a_glued_unit_keeps_its_case(x):
    """Changing the case of a unit or magnitude glued to a number in the only reading of the claim makes it fail, at every
    point of the chain. [M214]
    Why it matters for a score: `1M` is a million and `1m` a metre; case is part of a quantity."""
    with switches.set_all(True):
        toks = reader.tokenize(x)
    qs = [t for t in toks if t.cls == "Qty" and re.search(r"\d[A-Za-z]+$", t.text) and t.text.swapcase() != t.text]
    assume(len(qs) == 1 and len([t for t in toks if t.cls == "Qty"]) == 1 and len(toks) <= 12)
    q = qs[0]
    assume(x[q.start:q.end] == q.text)
    suffix = re.search(r"[A-Za-z]+$", q.text)[0]
    changed = x[: q.end - len(suffix)] + suffix.swapcase() + x[q.end:]
    for p in (chain.TEXT, chain.WORDS):
        assert not found(x, page(changed), p), (x, changed, p)


CIRCLED = ["①", "②", "③", "⑩", "⑪"]


@relation(HOLDS, domain="every loaded string with a digit x its first digit written as a circled digit, in the gold or in the page",
          pool="text, order, repeat, table_cell")
@LOOSE
@given(st.sampled_from([x for x in QTYS if re.search("[1-3]", x)]), st.booleans())
def test_a_circled_digit_is_the_digit(x, in_gold):
    """Writing a digit as its circled form, in the gold or in the page, leaves a text claim passing at Text, Cased and Words
    (a circled and a plain digit are the same enumerator). [M215]
    Why it matters for a score: models write `①` for a list's `1`; a careful reader takes them as one."""
    m = re.search("[1-3]", x)
    circled = x[: m.start()] + "①②③"[int(m[0]) - 1] + x[m.end():]
    assume(not re.search("[0-9]", x[m.end():m.end() + 1]) and not re.search("[0-9.,]", x[max(0, m.start() - 1):m.start()]))
    gold, out = (circled, x) if in_gold else (x, circled)
    for p in (chain.TEXT, chain.CASED, chain.WORDS):
        assert found(gold, page(out), p), (gold, out, p)


@relation(HOLDS, domain="pairs of different circled digits x a claim and a page that differ in them", pool="text, order, repeat, table_cell")
@given(st.sampled_from(CIRCLED), st.sampled_from(CIRCLED))
def test_two_different_circled_digits_are_two_numbers(a, b):
    """A claim of one circled digit is not found in a page of another circled digit, at any budget. [M216]
    Why it matters for a score: numbers are exact; `①` against `②` is `1` against `2`."""
    from omni_parse_bench import fold

    assume(fold.enumerator_digits(a) != fold.enumerator_digits(b))
    for p in (chain.TEXT, chain.WORDS):
        assert not found(a, page(b), p, 0 if p == chain.CASED else 1), (a, b, p)


@every_real_test("text strings", note="each written as the output, at Text, Cased and Words")
def test_every_real_text_string_written_as_the_output_passes():
    """Every real text string, written out as the page's only paragraph, is found at Text, at Cased and at Words, and
    its raw candidates only grow along the chain. [M205, M212]
    Why it matters for a score: as for M205 and M212, over the dataset's own strings."""
    n = 0
    for x in sorted({x for t in TESTS for x in text_strings(t.params)}):
        if not x.strip() or RESERVED.search(x):
            continue
        for p in (chain.TEXT, chain.CASED, chain.WORDS):
            assert found(x, page(x), p), (x, p)
        text, cased, words = (cands(x, page(x), p) for p in (chain.TEXT, chain.CASED, chain.WORDS))
        assert text <= cased <= words, x
        n += 1
    assert n, "no real string: the check is empty"
