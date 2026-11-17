"""Relations of number tests: a changed or added digit, and a changed separator (M12), and a number cut out of
a longer one (M20)."""
from __future__ import annotations

import unicodedata

from hypothesis import assume, given
from hypothesis import strategies as st

from metamorphic.common import NUMBER, HOLDS, escaped, every_real_test, passes, relation
from omni_parse_bench.scorers.unit_tests import runners


def one_digit_changed(s: str) -> list[str]:
    """`s` with one decimal digit (of any script) replaced by another digit of the same script, every way."""
    out = []
    for i, c in enumerate(s):
        if c.isdecimal():
            zero = ord(c) - unicodedata.digit(c)
            out += [s[:i] + chr(zero + d) + s[i + 1:] for d in range(10) if chr(zero + d) != c]
    return out


SEPARATORS = {",": ",", ".": ".", " ": " ", "\u202f": " "}     # a space of any width is a space


def one_separator_changed(s: str) -> list[str]:
    """`s` with one separator of its number (`,`, `.` or a space) dropped or swapped for another, or one added
    between two of its digits, every way."""
    s = s.strip()
    body = runners._NUMBER.match(s)
    a, z = body.start("body"), body.end("body")
    out = []
    for i in range(a, z):
        if s[i] in SEPARATORS:
            out += [s[:i] + s[i + 1:]] + [s[:i] + o + s[i + 1:] for o in ",. " if o != SEPARATORS[s[i]]]
        elif i + 1 < z and s[i].isdecimal() and s[i + 1].isdecimal():
            out += [s[:i + 1] + o + s[i + 1:] for o in ",. "]
    return out


def one_digit_glued(s: str) -> list[str]:
    """`s` with a digit glued before and after the digits of its number (inside its sign and percent)."""
    s = s.strip()
    body = runners._NUMBER.match(s)
    a, z = body.start("body"), body.end("body")
    zero = ord(s[a]) - unicodedata.digit(s[a])
    return [x for d in range(10) for x in (s[:a] + chr(zero + d) + s[a:], s[:z] + chr(zero + d) + s[z:])]


@relation(HOLDS, pool="number")
@given(st.sampled_from(NUMBER), st.data())
def test_changing_one_digit_of_a_number_fails_its_test(t, data):
    """A number test passes on its number as written and fails with any one of its digits changed. [M12a]
    Why it matters for a score: a misread digit is the error a number test exists to catch."""
    # Given a number test: it passes on its number as written
    s = t.params.content.number
    assert passes(t.params, f"<p>{escaped(s)}</p>")
    # When one digit is changed to another of its script; Then it fails
    changed = data.draw(st.sampled_from(one_digit_changed(s)))
    assert not passes(t.params, f"<p>{escaped(changed)}</p>"), changed


@relation(HOLDS, pool="number")
@given(st.sampled_from(NUMBER), st.data())
def test_a_digit_glued_to_a_number_fails_its_test(t, data):
    """A number test fails on its number with one more digit glued before or after it. [M12b]
    Why it matters for a score: '1,240' must not pass on '11,240' or '1,2405'."""
    # Given a number test; When a digit is glued before or after its digits; Then it fails
    glued = data.draw(st.sampled_from(one_digit_glued(t.params.content.number)))
    assert not passes(t.params, f"<p>{escaped(glued)}</p>"), glued


@every_real_test("number")
def test_every_real_number_test_fails_on_every_changed_or_glued_digit():
    """Every real number test fails with any digit of its number changed, or a digit glued on. [M12a, M12b]
    Why it matters for a score: as for M12a and M12b, over the whole dataset."""
    # Given every real number test; When each digit is changed, or a digit glued on; Then it fails
    bad = [(s, page) for t in NUMBER for s in [t.params.content.number]
           for page in (*one_digit_changed(s), *one_digit_glued(s))
           if passes(t.params, f"<p>{escaped(page)}</p>")]
    assert not bad, f"{len(bad)} changed numbers still pass, e.g. {bad[:8]}"


@relation(HOLDS)
@given(st.tuples(st.integers(1, 999), st.integers(1, 99)).map(lambda x: f"{x[0]}.{x[1]}"),
       st.sampled_from(".,"), st.integers(0, 9), st.sampled_from(["", "x ", "see "]))
def test_a_decimal_followed_by_a_point_and_a_digit_is_not_found(n, sep, d, before):
    """A decimal number (`12.5`) passes alone, before `.`, `,`, ` 7`, `, 7` or `. 7`, and in parentheses, and
    is not found where `.` or `,` and one or two digits follow it at once (`12.5.7`, `12.5,77`). [M20]
    Why it matters for a score: '12.5' cut out of '12.5.7' is a different number; '12.5.' ending a sentence is
    not."""
    p = runners.Present(runners.Number(n))
    # Given the number alone, or followed by a clean tail: it passes
    assert passes(p, f"<p>{before}{n}</p>")
    for tail in (".", ",", " 7", ", 7", ". 7"):
        assert passes(p, f"<p>{before}{n}{tail}</p>"), tail
    assert passes(p, f"<p>({n})</p>")
    # When a point or comma and one or two digits follow it at once; Then it fails
    assert not passes(p, f"<p>{before}{n}{sep}{d}</p>")
    assert not passes(p, f"<p>{before}{n}{sep}{d}{d}</p>")


@relation(HOLDS)
@given(st.integers(10, 10**7), st.sampled_from([",", ".", " ", ""]),
       st.sampled_from(["", ".5", ",25", ".125"]), st.sampled_from(["", "-"]), st.sampled_from(["", "%"]),
       st.data())
def test_a_number_fails_with_one_separator_dropped_added_or_swapped(whole, sep, frac, sign, pct, data):
    """A number test passes on its number with its separators as written, and fails with one separator
    (`,`, `.` or a space) dropped, swapped for another, or added between two of its digits (`1,240` fails on
    `1240`, `1.240`, `1 240` and `1,2,40`). [M12c]
    Why it matters for a score: a number printed with other punctuation is not the number the page prints."""
    # Given a number gold that loads; it passes on its number as written
    groups = [str(whole)[max(0, i - 3):i] for i in range(len(str(whole)), 0, -3)][::-1]
    gold = f"{sign}{sep.join(groups)}{frac}{pct}"
    assume(runners.number(gold) is not None and frac[:1] != sep)
    p = runners.Present(runners.Number(gold))
    assert passes(p, f"<p>{escaped(gold)}</p>")
    # When one separator is dropped, swapped or added; Then it fails
    changed = data.draw(st.sampled_from(one_separator_changed(gold)))
    assert not passes(p, f"<p>{escaped(changed)}</p>"), changed


@every_real_test("number")
def test_every_real_number_test_fails_on_every_changed_separator():
    """Every real number test fails with any one separator of its number dropped, swapped or added. [M12c]
    Why it matters for a score: as for M12c, over the whole dataset."""
    # Given every real number test; When each separator is dropped, swapped or added; Then it fails
    bad = [(s, page) for t in NUMBER for s in [t.params.content.number] for page in one_separator_changed(s)
           if passes(t.params, f"<p>{escaped(page)}</p>")]
    assert not bad, f"{len(bad)} changed numbers still pass, e.g. {bad[:8]}"
