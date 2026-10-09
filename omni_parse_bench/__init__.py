"""Omni Parse Bench: yes/no tests on single pages, graded against a provider's outputs.

A benchmark is a set of pages (manifest.parquet) and their tests (gold/). Each test is one yes/no
question about one page. A test reads one output of a prediction (its `output_type`), checks one
structure of it (its `test_type`) on pieces of the page's content (its `args`), and is tagged with
what that content is (its `tags`: in a table, handwritten, Thai, ...), which selects tests and never
changes a verdict:

    from omni_parse_bench import gold, score, summarize

    pages, tests = gold.load("dataset/")         # manifest.parquet and gold/*.json
    by_page = gold.by_page(tests)
    verdicts = [v for p in pages for v in score(outputs[p.page_id], by_page[p.page_id])]
    summary = summarize(verdicts, tests, pages)

`score` is pure: no files, no network. Producing the outputs is `omni_parse_bench.harness`
(`pip install 'omni-parse-bench[harness]'`), and nothing here imports it.

See docs/design.md for the full design.
"""
from omni_parse_bench import gold
from omni_parse_bench.metric import Verdict, score, summarize

__all__ = ["gold", "score", "summarize", "Verdict"]
