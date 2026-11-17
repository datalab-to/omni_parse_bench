"""The restatement of fold's leader rule that M14 skips deletions by (test_fold_and_case.py) agrees with the
scorer on fixed texts: a deletion it skips as part of a leader run leaves the test passing, and
one it does not skip makes the test fail. This is the check that the restatement neither hides a deletion that
changes the verdict (a skip too many) nor reports one that cannot (a skip too few)."""
from __future__ import annotations

import pytest

from metamorphic.common import escaped, passes
from metamorphic.test_fold_and_case import why_a_deletion_cannot_count
from omni_parse_bench.scorers.unit_tests import runners

LEADER_TEXTS = [
    "Hevesy Istvan . . . . . Julius Knaack",
    "Name . . . 12",                 # exactly 3 items: deleting one dot changes the fold
    "Name ... 12",
    "Name . . . . 12",
    "Name .  .   .   . 12",
    "Net income . . . . -4.8",       # a sign after a spaced leader is a sign, not a leader item
    "Net income ....-4.8",
    "Net income . . . . - 4.8",
    "Name · · · · 12",   # middle dots
    "Name ···· 12",
    "Name . · . · 12",
    "Name _ _ _ _ 12",
    "Name = = = = 12",
    "Name * * * * 12",
    "Name …… 12",         # an ellipsis is three items
    "Name … 12",
    "Name . … 12",
    "Name … … … … 12",
    "U.S. . . . 12",
    "Fig. 3. . . 10",
    "Total — — — — 12",
    "Total ―――― 12",
    "Total . . . . −5",
    # a leader at an end of the text: fold drops it from the gold, whatever its length
    "Total ...",
    "Total...",
    "... Total",
    "Total . . .",
    "Total …",
    "Total … ",
    "Total ..",
    # from the published dataset's exact tests (panel questions and signature lines)
    "Character: quiet, active, kind, funny ...",
    "Other symptoms/problems related to...",
    "DocuSigned by: Mark Worman 70ABE377123E401...",
]


@pytest.mark.parametrize("text", LEADER_TEXTS)
def test_the_leader_restatement_agrees_with_the_scorer_on_each_deletion(text):
    p = runners.Present(runners.Text(text, 0))
    assert passes(p, f"<p>{escaped(text)}</p>")
    for i, c in enumerate(text):
        why = why_a_deletion_cannot_count(text, i)
        if why not in (None, "part of a leader run"):
            continue
        gone = text[:i] + text[i + 1:]
        ok = passes(p, f"<p>{escaped(gone)}</p>")
        assert ok == (why == "part of a leader run"), (text, i, c, why, ok)
