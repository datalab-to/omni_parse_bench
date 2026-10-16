"""The scorers: each is a package that owns the shape of the gold it reads, and grades a page's outputs
against it with `gold(page)`, `score(pred, gold, ...)`, `lines(...)` and `summarize(lines)`.

    unit_tests    yes/no tests on single pages: what Omni Parse Bench publishes

omni-parse-bench has one. Code shared by scorers (reading html as text, folding text, tables,
equations, the vocabulary) stays at the package's top, so a scorer of your own can use it too.
"""
