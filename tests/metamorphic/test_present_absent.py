# ruff: noqa: E501
"""Relations of `present` tests with `{"absent": true}` (M170 to M173): an absent test is the negation of a `present` test of the same
text arg on the page's visible text (an image description is not read); a known wrong reading written anywhere
a reader sees it, or a near copy within the budget, fails; a copy with one of its numbers changed passes."""
from __future__ import annotations

import re

from hypothesis import given
from hypothesis import strategies as st

from metamorphic.common import HOLDS, TESTS, escaped, relation, text_strings
from omni_parse_bench import markdown, normalize, views
from omni_parse_bench.scorers.unit_tests import runners


def strings() -> list[str]:
    """The loaded text strings an absent test may hold: 20 or more characters after fold."""
    out = {x for t in TESTS for x in text_strings(t.params) if len(normalize.fold(x)) >= runners.ABSENT_MIN_CHARS}
    return sorted(out)


def budget(x: str) -> int:
    return int(len(normalize.fold(x)) * runners.ABSENT_MAX_DIFFS_SHARE)


def absent(x: str, md: int, page: str) -> bool:
    return runners.present(runners.Present(runners.Text(x, md), absent=True), views.html(page))[0]


def present(x: str, md: int, page: str) -> bool:
    return runners.present(runners.Present(runners.Text(x, md)), views.html(page))[0]


# Places a reader sees; the reading is written between two words of other text, set apart by ";" so that no
# punctuation of the string runs into theirs.
PLACES = {
    "paragraph": lambda x: f"<p>Before.</p><p>{x}</p><p>After.</p>",
    "inline": lambda x: f"<p>Before; {x}; after</p>",
    "table cell": lambda x: f"<table><tr><td>Name</td><td>{x}</td></tr></table>",
    "list item": lambda x: f"<ul><li>One</li><li>{x}</li></ul>",
    "heading": lambda x: f"<h2>{x}</h2><p>Body.</p>",
    "written twice": lambda x: f"<p>{x}</p><p>Then.</p><p>{x}</p>",
    "markdown": lambda x: x,
}
# Note: a markdown writer escapes what would be read as markup: a block marker at the start of the line (a
# heading's "#", a list's "-", "1."), and emphasis, code, link and html marks anywhere.
_MD_BLOCK = re.compile(r"^(\s*)(#{1,6}(?=\s|$)|[-+*>](?=\s|$)|\d+(?=[.)](?:\s|$))|=+\s*$|-{3,})")
_MD_INLINE = re.compile(r"([*_`])")
# Note: a bracket or an angle bracket is written as its entity: "\\[" would open a math span.
_MD_ENTITY = {ord("["): "&#91;", ord("]"): "&#93;", ord("<"): "&lt;", ord(">"): "&gt;", ord("&"): "&amp;"}


def md_escaped(x: str) -> str:
    return _MD_BLOCK.sub(r"\1\\\2", _MD_INLINE.sub(r"\\\1", x.translate(_MD_ENTITY)))


def page_of(place: str, x: str) -> str:
    if place == "markdown":
        return markdown.to_html(f"Before.\n\n{md_escaped(x)}\n\nAfter.") if x else markdown.to_html("Before.\n\nAfter.")
    return PLACES[place](escaped(x))


@relation(HOLDS, domain="every loaded text string of 20+ folded characters x 3 budgets (0, half the cap, the cap) "
                        "x 7 pages (empty, the string, a character dropped, a character doubled, its words "
                        "reversed, the string beside other text, the string as an image description)",
          pool="text, order, repeat, table_cell")
def test_an_absent_test_is_the_negation_of_a_present_test_on_the_visible_page():
    """For each loaded text string of 20 or more folded characters, an absent test with a budget of 0, half the
    cap or the cap (a quarter of its folded length) passes exactly where a `present` test of the same text arg
    fails on the page's visible html (the page with its images left out): on an empty page, the string, the
    string with a character dropped or doubled, its words reversed, the string beside other text, and the
    string written only as an image description, where `present` passes and the absent test passes too. [M170]
    Why it matters for a score: an absent test inherits every rule of the `present` search (fold, numbers, glued words,
    line hyphens) and no other, on what the page shows, so what `present` would credit as the reading in the
    visible text, an absent test faults, and a figure's description is never faulted."""
    xs, bad, n = strings(), [], 0
    assert xs, "no loaded text string of 20 or more folded characters"
    for x in xs:
        mid = len(x) // 2
        texts = ["", x, x[:mid] + x[mid + 1:], x[:mid] + x[mid] + x[mid:], " ".join(x.split()[::-1]),
                 f"Before. {x} After."]
        alt = x.replace('"', "&quot;").replace("<", "&lt;")
        pages = [(f"<p>{escaped(t)}</p>" if t else "", f"<p>{escaped(t)}</p>" if t else "") for t in texts]
        pages.append((f'<p>Before.</p><img alt="{alt}">', "<p>Before.</p>"))
        for md in sorted({0, budget(x) // 2, budget(x)}):
            for html, visible in pages:
                n += 1
                if absent(x, md, html) is present(x, md, visible):
                    bad.append((x[:40], md, html[:40]))
            if not (present(x, md, pages[-1][0]) and absent(x, md, pages[-1][0])):
                bad.append((x[:40], md, "image description: present and absent should both pass"))
    assert not bad, f"{len(bad)} of {n} cases break, e.g. {bad[:5]}"


@relation(HOLDS, domain="every loaded text string of 20+ folded characters x 7 places a reader sees (a paragraph, "
                        "inline, a table cell, a list item, a heading, written twice, markdown with its markup "
                        "escaped) x 2 states (written, left out)", pool="text, order, repeat, table_cell")
def test_a_reading_written_anywhere_visible_fails_and_left_out_passes():
    """Each loaded text string of 20 or more folded characters, as a known wrong reading with no budget, fails
    an output that writes it in a paragraph, inline, in a table cell, in a list item, in a heading, twice, or in
    markdown, and passes the same output with it left out. Each written page is first checked to hold the
    string, as `present` finds it: a page that does not is the generator's error, reported apart. [M171]
    Why it matters for a score: the wrong reading is faulted wherever the output shows it, and the page around
    it costs nothing."""
    xs, bad, unfaithful = strings(), [], []
    for x in xs:
        for place in PLACES:
            page = page_of(place, x)
            if not present(x, 0, page):
                unfaithful.append((x[:40], place))
            elif absent(x, 0, page):
                bad.append((x[:40], place, "written"))
            if not absent(x, 0, page_of(place, "")):
                bad.append((x[:40], place, "left out"))
    assert xs and not unfaithful, f"{len(unfaithful)} generated pages do not hold their string, e.g. {unfaithful[:5]}"
    assert not bad, f"{len(bad)} of {len(xs) * 2 * len(PLACES)} cases break, e.g. {bad[:5]}"


LETTER = re.compile(r"[^\W\d_]")


@relation(HOLDS, domain="12 wrong readings (a name, a line, a code) x 1 to the cap letter substitutions at "
                        "spread positions x 7 places")
@given(st.sampled_from(["Johnathan Quincy Smithers", "Chapter 4. The harbor at night", "Margarethe von Altenburg-Hesse",
                        "Received from the Treasurer", "The meeting is adjourned sine die.",
                        "Signed in the presence of witnesses", "Dr. Aurelio Benedetti-Ruiz Jr.", "Lot 17, Block C, Plan 4402",
                        "Not to be removed from the library", "Second reading: amended clause four",
                        "Patient refused the procedure", "Estimated arrival: early spring"]),
       st.data(), st.sampled_from(list(PLACES)))
def test_a_near_copy_within_the_budget_fails(x, data, place):
    """A known wrong reading with k of its letters replaced (k from 1 to its budget, a quarter of its folded
    length, at positions at least two apart), written in any of the places above, fails a test with that
    budget. [M172]
    Why it matters for a score: a system that misreads a few letters of the hidden text has still read it,
    and the budget catches it."""
    md = budget(x)
    spots = [i for i, c in enumerate(x) if LETTER.match(c)]
    k = data.draw(st.integers(1, md))
    chosen = sorted(data.draw(st.lists(st.sampled_from(spots), min_size=k, max_size=k, unique=True)))
    if any(b - a < 2 for a, b in zip(chosen, chosen[1:], strict=False)):
        chosen = chosen[:1]
    near = "".join(("z" if c.lower() != "z" else "q") if i in chosen else c for i, c in enumerate(x))
    assert not absent(x, md, page_of(place, near)), (near, place)


@relation(HOLDS, domain="every loaded text string of 20+ folded characters holding a digit x each of its "
                        "numbers with one digit changed x 3 budgets (0, half the cap, the cap)",
          pool="text, order, repeat, table_cell")
def test_a_copy_with_a_number_changed_passes_at_any_budget():
    """Each loaded text string of 20 or more folded characters that holds a digit, written with the last digit
    of one of its numbers changed, passes an absent test of the string at a budget of 0, half the cap or the
    cap: numbers are exact, as in `present`. [M173]
    Why it matters for a score: a page that prints a different number than the wrong reading does not hold the
    reading, so a faithful output there is never faulted."""
    xs, n, bad = [x for x in strings() if re.search(r"\d", x)], 0, []
    for x in xs:
        for m in re.finditer(r"\d+", x):
            j = m.end() - 1
            changed = x[:j] + str((int(x[j]) + 1) % 10) + x[j + 1:]
            n += 1
            for md in sorted({0, budget(x) // 2, budget(x)}):
                if not absent(x, md, f"<p>{escaped(changed)}</p>"):
                    bad.append((x[:40], changed[:40], md))
    assert n, "no loaded string of 20 or more folded characters holds a digit"
    assert not bad, f"{len(bad)} cases break, e.g. {bad[:5]}"
