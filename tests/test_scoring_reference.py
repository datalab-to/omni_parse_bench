"""The scoring reference (docs/scoring) is checked against the code.

Every rules table in those pages is generated from the cases in tests/scoring_probes (`render.py`), and each
case states what it expects (a mark I, B or P, or a reading). These tests run every case in a clean subprocess
and fail when:

- a case no longer gives what it claims (the page would now say something false);
- the record `tests/scoring_probes/observed.txt` differs from a fresh run (a why or a reading changed);
- a page's generated tables differ from what the record renders to (edited by hand, or not rewritten);
- a page cites `(case label)` for a label that does not exist, or a table id is missing from its page.

After a deliberate scorer change, update the cases that changed (mark, expectation, rule) and the prose that
cites them, then rewrite the record and the tables:

    python tests/test_scoring_reference.py --regenerate   # = python tests/scoring_probes/render.py --write
"""
from __future__ import annotations

import difflib
import functools
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "tests" / "scoring_probes")]

import render  # noqa: E402
from cases import cited  # noqa: E402

REGENERATE = "python tests/test_scoring_reference.py --regenerate"


@functools.cache
def fresh() -> str:
    record, err, code = render.record_in_subprocess()
    assert code == 0 and not err.strip(), f"the cases exited {code} or wrote to stderr:\n{err[-2000:]}"
    return record


def test_every_case_still_gives_what_it_claims():
    bad = render.broken(render.load(), fresh())
    assert not bad, ("A scorer change made these documented claims false. Update each case (mark, "
                     f"expectation, rule) and the prose that cites it, then run {REGENERATE}:\n  "
                     + "\n  ".join(bad))


def test_the_record_is_up_to_date():
    want, got = render.parse(render.OBSERVED.read_text(encoding="utf-8")), render.parse(fresh())
    hunks = []
    for t in sorted(set(want) | set(got)):
        if want.get(t) != got.get(t):
            a = [f"{k}\t{' | '.join(v)}" for k, v in want.get(t, {}).items()]
            b = [f"{k}\t{' | '.join(v)}" for k, v in got.get(t, {}).items()]
            d = difflib.unified_diff(a, b, f"observed.txt [{t}]", f"now [{t}]", lineterm="", n=0)
            hunks.append("\n".join(d))
    assert not hunks, (f"The recorded results changed; check the pages that show them, then run {REGENERATE}:"
                       "\n\n" + "\n\n".join(hunks))


def test_the_pages_show_the_record():
    pages = render.load()
    made = render.blocks(pages, render.OBSERVED.read_text(encoding="utf-8"))
    stale = []
    for page, blocks in made.items():
        text = (render.DOCS / page).read_text(encoding="utf-8")
        new, odd = render.rewrite(text, blocks)
        assert not odd, f"{page}: generated blocks missing or unknown: {odd}"
        if new != text:
            stale.append(page)
    assert not stale, f"These pages' generated tables are out of date (edited by hand?); run {REGENERATE}: " \
        f"{stale}"


def test_every_cited_case_exists():
    labels = {c.label for tables, _ in render.load().values() for t in tables for c in t.cases}
    missing = [f"{p.name}: {x}" for p in sorted(render.DOCS.glob("*.md"))
               for x in cited(p.read_text(encoding="utf-8")) if x not in labels]
    assert not missing, "These pages cite cases that do not exist:\n  " + "\n  ".join(missing)


def test_the_blind_spots_listed_in_the_readme_are_blind():
    marks = {c.label: c.mark for tables, _ in render.load().values() for t in tables for c in t.cases}
    text = (render.DOCS / "README.md").read_text(encoding="utf-8")
    section = text.split("## What the tests cannot see", 1)[1].split("\n## ", 1)[0]
    wrong = [x for x in cited(section) if marks.get(x) != "B"]
    assert not wrong, f"README.md lists these as blind spots, but their cases are not marked B: {wrong}"


if __name__ == "__main__":
    if sys.argv[1:] != ["--regenerate"]:
        print(__doc__)
        sys.exit(2)
    sys.exit(render.write())
