# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](./pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](./LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](./licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)

A document-parsing benchmark. Every test is a yes/no question about one page: is this text in the
output, in this order, in a table cell under these headings, in a layout block of this kind?

The pages are PubMed Central tables, arXiv math, old scans, multi-column and tiny text, real
business documents, filled forms (US federal, French, handwritten), handwritten manuscripts,
engineering drawings, pages in many languages, and rotated, skewed and rebuilt copies. Each test's
answer comes from a source we can check: the publisher's XML, the PDF's text layer, a form we
filled, an archive's transcription, or a model panel, with a person deciding its splits.

This repository runs the benchmark on [our dataset](https://huggingface.co/datasets/datalab-to/omni_parse_bench)
or yours, and exposes its two primitives, `predict` and `score`, for your pipelines.

- [Install](#install)
- [Run the benchmark](#run-the-benchmark)
- [Score](#score)
- [Predict](#predict)
- [Documentation](#documentation)
- [License](#license)
- [Citation](#citation)

## Install

```bash
uv pip install 'omni-parse-bench @ git+https://github.com/datalab-to/omni_parse_bench'               # score(): no network, no API keys
uv pip install 'omni-parse-bench[harness] @ git+https://github.com/datalab-to/omni_parse_bench'      # + vendor adapters, to predict
uv pip install 'omni-parse-bench[benchmark] @ git+https://github.com/datalab-to/omni_parse_bench'    # + dataset access, to run the benchmark
```

## Run the benchmark

With `[benchmark]` installed, run vendors on the dataset (5 pages here):

```bash
opb benchmark --out runs/ --limit 5 --providers datalab openai/gpt-5.6-sol
```

It shows the plan and asks before calling any vendor, since calls cost money. Each vendor needs its
API key in the environment: `DATALAB_API_KEY` for Datalab, `OPENROUTER_API_KEY` for any model by
its OpenRouter id; [`docs/providers.md`](./docs/providers.md) lists the rest. A run is resumable: stop it, and run the same command again to carry
on.

Each setting of a provider is its own run; here, two:

```bash
opb benchmark --out runs/ --limit 5 --providers datalab \
  --options '{"datalab": [{"mode": "balanced"}, {"mode": "accurate"}]}'
```

`--dataset` picks the dataset: a folder, or `hf://datasets/<repo>[@revision]` (ours by default).
`--suites`, `--sample` and `--pages` choose pages. [`docs/API.md`](./docs/API.md#benchmark) has
every option, how resuming works and what a run writes. Each run's `scores.jsonl` has one line per
test; [Asking a question](./docs/API.md#asking-a-question) shows how to compare runs by tag, suite or
test type.

## Score

Here is one page with three tests, written inline with `gold.parse` so the gold
file's shape is visible (`gold.read("gold/<page_id>.json")` reads a file):

```python
from omni_parse_bench import gold, score, summarize

tests = gold.parse("example-p1", {"tests": [
    {
        "id": "t1",
        "test_type": "present",
        "output_type": "html",
        "derivation": "text_layer",
        "tags": ["Latn", "eng"],
        "args": {"content": {"text": "Quarterly revenue rose 12%", "max_diffs": 1}},
        "settings": {},
    },
    {
        "id": "t2",
        "test_type": "order",
        "output_type": "html",
        "derivation": "text_layer",
        "tags": ["Latn", "eng", "heading"],
        "args": {
            "before": {"text": "Summary", "max_diffs": 0},
            "after": {"text": "Outlook", "max_diffs": 0},
        },
        "settings": {},
    },
    {
        "id": "t3",
        "test_type": "table_cell",
        "output_type": "html",
        "derivation": "publisher_markup",
        "tags": ["table"],
        "args": {
            "cell": {"text": "4.2", "max_diffs": 0},
            "top_heading": {"text": "Q3", "max_diffs": 0},
        },
        "settings": {},
    },
]})

outputs = {
    "html": (
        "<h2>Summary</h2>"
        "<p>Quarterly revenue rose 12% on the year.</p>"
        "<table>"
        "<tr><th>Q2</th><th>Q3</th></tr>"
        "<tr><td>3.9</td><td>4.1</td></tr>"
        "</table>"
        "<h2>Outlook</h2>"
    ),
}
verdicts = score(outputs, tests)
```

```python
>>> verdicts
[Verdict(id='t1', result='pass', why=''),
 Verdict(id='t2', result='pass', why=''),
 Verdict(id='t3', result='fail', why="no cell matching '4.2' in any table")]

>>> s = summarize(verdicts, tests)["html"]
>>> s["score"], s["per_test_type"], s["per_tag"]["table"]
(0.6666666666666666, {'present': 1.0, 'order': 1.0, 'table_cell': 0.0}, {'score': 0.0, 'tests': 1, 'pages': 1})
```

A verdict is `pass`, `fail`, `unsupported` (the provider can't produce that output) or `error`
(grading raised: a bug in the scorer, not the provider's fault), with `why` saying what went wrong.
`unsupported` and `error` verdicts are left out of every score.

From the command line, with the outputs in a JSON file:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json
```

It prints the verdicts. A score is a number over many pages: `summarize` in your code, or
`summary.json` from `opb benchmark`. To grade your own model on the whole dataset, see
[The dataset](./docs/API.md#the-dataset).

## Predict

With `[harness]` installed, predict with our provider adapters:

```python
from omni_parse_bench import harness

record = harness.predict("datalab", "pages/<page_id>.pdf", {"html", "blocks"}, mode="balanced")
record["outputs"]       # {"html": "...", "blocks": [...]}
record["errors"]        # {output: why} for anything that failed
record["calls"]         # what was sent, cost, wall time

score(record["outputs"], gold.read("gold/<page_id>.json"))
```

From the command line:

```bash
opb predict --provider openai/gpt-5.6-sol --page pages/<page_id>.pdf --wants html
opb providers        # every provider, and its options
```

Every provider gets the same timeout per call and its most accurate settings by default. An output a vendor
can't produce is recorded as unsupported, and its tests are left out of that vendor's scores rather
than failed.

## Documentation

- [`docs/API.md`](./docs/API.md): every function and command, the dataset, and what a run writes;
- [`docs/design.md`](./docs/design.md): each test type, tag and derivation, and the data layout;
- [`docs/building-tests.md`](./docs/building-tests.md): how the tests were built, and where each
  one's answer comes from;
- [`docs/providers.md`](./docs/providers.md): the provider adapters; and
- [`docs/tagging.md`](./docs/tagging.md): how the tests' tags were made.

Found a test that's wrong, or a page you hold rights in? [Open an issue](https://github.com/datalab-to/omni_parse_bench/issues).

## License

The code is Apache 2.0: see [`LICENSE`](./LICENSE), and [`NOTICE`](./NOTICE) for the third-party
code it includes (KaTeX, MIT; a rewrite of olmOCR-bench's table parser, Apache 2.0).

The data's licenses are per source. Each source of the pages, its license and the credit it
requires are in [`licenses/`](./licenses), one file per source. The tests are CC BY 4.0, except
those converted from olmOCR-bench (ODC-BY 1.0) and fr-bench-pdf2md (MIT), and those quoting
Wikipedia on three handwriting pages (CC BY-SA 4.0).

## Citation

```bibtex
@misc{omniparsebench2026,
  title        = {Omni Parse Bench: A Document-Parsing Benchmark},
  author       = {{Datalab}},
  year         = {2026},
  howpublished = {\url{https://github.com/datalab-to/omni_parse_bench}},
}
```

Please also cite the upstream datasets whose pages or tests this benchmark uses; they are listed
in [`licenses/`](./licenses).
