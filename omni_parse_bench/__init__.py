"""Omni Parse Bench: yes/no tests on single pages, graded against a provider's outputs.

A benchmark is a set of pages (manifest.parquet) and their tests (gold/). Each test is one yes/no
question about one page. A test reads one output of a prediction (its `output_type`), checks one
structure of it (its `test_type`) on pieces of the page's content (its `args`), and is tagged with
what that content is (its `tags`: in a table, handwritten, Thai, ...), which selects tests and never
changes a verdict:

    from omni_parse_bench import data
    from omni_parse_bench.scorers import unit_tests

    _, pages = data.read_manifest("dataset/")    # manifest.parquet; p.doc_path is the page's file
    xs = []
    for p in pages:
        tests = unit_tests.gold(p)                # gold/<page_id>.json, read and checked
        xs += unit_tests.lines(unit_tests.score(preds[p.page_id], tests), tests, p)
    summary = unit_tests.summarize(xs)

`score` is pure: no files, no network. Producing the predictions is `omni_parse_bench.harness`
(`pip install 'omni-parse-bench[harness]'`), and nothing here imports it.

See docs/design.md for the full design.
"""
from omni_parse_bench import data, scorers
from omni_parse_bench.scorers.unit_tests import Verdict, lines, score, summarize

__all__ = ["data", "lines", "score", "scorers", "summarize", "Verdict"]
