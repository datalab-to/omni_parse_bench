"""Omni Parse Bench: yes/no tests on single pages, graded against a provider's outputs.

`data` reads a dataset's pages, `task` is the parse task, `benchmark.default()` is the whole benchmark, and
`scorers.unit_tests` grades on its own: `score` is pure, with no files and no network. Producing
predictions is `harness` (`pip install 'omni-parse-bench[harness]'`), which the scorer never imports.
docs/design.md has the full design.
"""
from omni_parse_bench import data, scorers
from omni_parse_bench.scorers.unit_tests import UnitTests, Verdict, check, gold, lines, score, summarize

__all__ = ["check", "data", "gold", "lines", "score", "scorers", "summarize", "UnitTests", "Verdict"]
