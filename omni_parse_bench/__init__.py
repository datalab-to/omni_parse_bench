"""Omni Parse Bench: yes/no tests on single pages, graded against a system's outputs.

- `data`: a dataset's pages;
- `task`: the parse task;
- `benchmark.default()`: the whole benchmark;
- `scorers.unit_tests`: grading, on its own, with no files and no network; and
- `harness`: producing predictions (`pip install 'omni-parse-bench[harness]'`), which grading never imports.

docs/design.md has the full design.
"""
from omni_parse_bench import data, scorers
from omni_parse_bench.scorers.unit_tests import UnitTests, Verdict, check, gold, lines, score, summarize

__all__ = ["check", "data", "gold", "lines", "score", "scorers", "summarize", "UnitTests", "Verdict"]
