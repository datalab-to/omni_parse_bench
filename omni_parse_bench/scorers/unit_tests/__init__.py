"""The unit-test scorer: yes/no tests on single pages. Its public functions are imported here.

    tests.py        what a test is, and how a page's gold file of tests is read and checked
    runners.py      how each test type is run on an output
    compare.py      one page: every test run against its outputs, a verdict each (`score`)
    unit_tests.py   a dataset: each page's tests read and checked, the verdicts summarized, and `UnitTests`,
                    the scorer as omni-bench-core grades a run
"""
from . import compare, runners, tests
from .compare import Verdict, score
from .tests import GoldError, Test
from .unit_tests import UnitTests, check, gold, lines, summarize

__all__ = ["GoldError", "Test", "UnitTests", "Verdict", "check", "compare", "gold", "lines", "runners",
           "score", "summarize", "tests"]
