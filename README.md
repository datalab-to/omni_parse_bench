# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)

Omni Parse Bench (OPB) tests document parsers with 16,288 unit tests on 2,937 pages. Each test is a yes/no question
about one page (this text is present, this cell sits under these headings, this line is a heading), checked by plain
code: no model sits in the scorer. Every test carries its provenance.

**Built by Datalab, whose systems are on the leaderboard (marked).** Every test, run and verdict is public, so you can
check any row. The dataset is on [Hugging Face](https://huggingface.co/datasets/datalab-to/omni_parse_bench).

## Leaderboard

| parser | weights | headline | text | tables | layout | USD / 1,000 pages |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| Gemini 4 Argon † | closed | 96.0 | 94.4 | 97.1 | 96.4 | $49.88 ‡ |
| Gemini 4 Carbon † | closed | 95.7 | 94.7 | 97.1 | 95.2 | $58.73 ‡ |
| Datalab accurate (Datalab) | closed | 94.7 | 92.6 | 95.4 | 96.0 | $7.50 |
| Datalab balanced (Datalab) | closed | 93.7 | 90.7 | 94.3 | 96.1 | $3.00 |
| Gemini 3.8 Flash * | closed | 92.5 | 92.0 | 95.3 | 90.3 | ≈$37.08 |
| Reducto | closed | 91.1 | 86.0 | 91.4 | 95.8 | $10.00 |
| LlamaParse | closed | 90.8 | 89.4 | 92.9 | 90.0 | ≈$31.25 |
| chandra-ocr-2 (Datalab) | open | 90.4 | 87.9 | 88.0 | 95.4 | — |
| Mistral OCR | closed | 89.9 | 83.6 | 92.2 | 93.8 | $4.00 |
| Claude Sonnet 5.5 * | closed | 88.9 | 93.7 | 95.5 | 77.5 | ≈$34.30 |
| dots.mocr | open | 88.2 | 83.1 | 89.0 | 92.5 | — |
| GPT-5.6 Sol | closed | 87.9 | 86.0 | 91.9 | 85.9 | ≈$94.49 |
| MinerU2.5-Pro | open | 87.4 | 78.0 | 92.5 | 91.7 | — |
| Infinity-Parser2-Pro | open | 87.4 | 83.9 | 84.6 | 93.5 | — |
| OCRia-1 (+ vendor grounding, Docling Heron) | open | 87.1 | 82.7 | 84.9 | 93.8 | — |
| Surya OCR 2.5 (Datalab) | open | 86.3 | 84.3 | 78.8 | 95.8 | — |
| OXR-1.0 | open | 85.6 | 77.0 | 88.3 | 91.4 | — |
| OvisOCR3 | open | 84.5 | 78.2 | 84.7 | 90.6 | — |
| MiniCPM-OCR-1.0 | open | 83.5 | 73.4 | 89.5 | 87.6 | — |
| Extend | closed | 83.4 | 64.2 | 92.7 | 93.4 | ≈$33.75 |
| Azure | closed | 83.4 | 75.2 | 82.3 | 92.8 | $5.00 |
| Surya OCR 2 (Datalab) | open | 83.3 | 81.2 | 74.6 | 94.3 | — |
| LightOnOCR-3-4B | open | 83.1 | 84.4 | 70.9 | 94.0 | — |
| Nemotron 3.5 Parse | open | 82.3 | 73.7 | 82.7 | 90.5 | — |
| LightOnOCR-3-0.8B | open | 81.9 | 81.7 | 72.2 | 91.7 | — |
| GLM-OCR | open | 81.9 | 71.6 | 84.7 | 89.3 | — |
| Unlimited-OCR 2 | open | 81.5 | 73.0 | 80.0 | 91.6 | — |
| PaddleOCR-VL-1.6 | open | 81.3 | 69.2 | 84.0 | 90.7 | — |
| MonkeyOCR | open | 79.9 | 70.3 | 79.6 | 89.8 | — |
| Unlimited-OCR | open | 79.5 | 70.7 | 76.6 | 91.1 | — |
| Indra OCR (Datalab) | open | 78.8 | 68.0 | 75.8 | 92.6 | — |
| Infinity-Parser2-Flash | open | 78.7 | 78.8 | 66.8 | 90.4 | — |
| DeepSeek-OCR-2 | open | 75.4 | 64.6 | 70.2 | 91.4 | — |
| LiteParse (ocria-nano) | open | 74.8 | 59.4 | 74.1 | 90.9 | — |
| HunyuanOCR-1.5 | open | 68.8 | 62.3 | 62.6 | 81.4 | — |
| Docling (formula) | open | 66.9 | 46.4 | 63.8 | 90.6 | — |
| Docling | open | 64.5 | 39.1 | 63.8 | 90.6 | — |
| PP-StructureV3 | open | 59.2 | 55.8 | 48.5 | 73.2 | — |
| PyMuPDF4LLM (OCR) | open | 51.5 | 26.5 | 42.1 | 86.0 | — |
| LiteParse (Tesseract) | open | 42.3 | 43.6 | 14.5 | 68.8 | — |
| PyMuPDF4LLM | open | 41.2 | 17.7 | 42.0 | 64.0 | — |
| LiteParse | open | 35.0 | 37.9 | 14.3 | 52.8 | — |
| OpenDataLoader | open | 23.6 | 17.9 | 5.4 | 47.4 | — |

Rows marked **(Datalab)** are Datalab's systems. Rows marked \* are models that helped make or verify tests, which may favor them.

**About these results**

- **Scorer:** omni-parse-bench 1.8.0 ([release notes](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/release-notes/v1.8.0.md)). The pending-regrade rows below are on an older scorer.
- **How systems were run:** most rows are saved predictions regraded with no new calls; Gemini 4, Indra OCR, OCRia-1, Docling and the layout of two models are new runs ([release notes](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/release-notes/v1.8.0.md)); settings for each row are in [docs/providers.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md). Open tools run locally are fresh full runs.
- **Failed pages count as failed**, with all their tests failed, except † below.
- \* Models that helped make or verify tests: 1,312 of the 8,499 text tests (15%) have a model-derived answer (derivation field `model_panel` or `model_review`) from Gemini 3.8 Flash, Claude Opus 5.5 or Claude Sonnet 5.5 (the data does not record which), and all 2,403 layout tests are `model_panel`. [Details](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/leaderboard.md#starred-rows).
- † **Gemini 4 got a second chance: no other system did.** Its rows combine one full pass with one rerun of the pages that pass failed. The first pass alone scores 85.0 (Argon) and 83.7 (Carbon). A single retry policy for all systems is planned.
- **Price** is the list price for one pass over 1,000 pages, in USD; `≈` marks an estimate. Open models run on your hardware, so they have none here. ‡ Gemini 4's reported cost includes its reruns, so it is not a single-pass price ([details](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/leaderboard.md#price-per-1000-pages)).
- Layout scores of Gemini 3.8 Flash and GPT-5.6 Sol come from a separate run that asked each model for blocks.
- Differences under about one point are not meaningful.
- Vendors: open an issue to correct your system's settings or price.

### Pending regrade

These rows are still graded by omni-parse-bench 1.5.0, so they are not comparable with the table above.

| parser | weights | headline | text | tables | layout | USD / 1,000 pages |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| GPT-6.1 Sol | closed | 91.5 | 89.8 | 95.6 | 89.1 | $30.95 |
| Claude Opus 5.5 * | closed | 90.0 | 93.9 | 93.4 | 82.6 | $68.45 |

### No layout output (no headline)

These systems return text and tables but no layout blocks, so they have no headline.

| parser | weights | text | tables |
| --- | --- | ---: | ---: |
| OvisOCR2 | open | 74.2 | 79.9 |
| Xiaomi-OCR-0 | open | 73.7 | 90.6 |
| OvisOCR | open | 72.2 | 78.2 |
| olmOCR-2 | open | 71.8 | 56.6 |
| Nanonets-OCR2-3B | open | 69.0 | 62.6 |
| pdf-inspector (OCR) | open | 41.4 | 17.7 |
| pdf-inspector | open | 20.6 | 17.0 |
| pdftext | open | 20.6 | 0.0 |
| pdftotext | open | 20.4 | 0.0 |
| Tesseract | open | 17.7 | 0.0 |
| MarkItDown | open | 16.0 | 13.9 |

More: all columns (parameters, refusals), the hard slices, the latency and price charts and per-row run notes are in [docs/leaderboard.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/leaderboard.md).

## What it measures

A test belongs to one of four families; the first three make the headline, their mean.

| test type | checks | family |
|---|---|---|
| `present` | this text, number or equation appears | text |
| `order` | text A comes before text B | text |
| `repeat` | this line appears exactly N times | text |
| `page_near_empty` | a blank page yields at most N non-space characters | text |
| `verbatim` | the text between two anchors is this, verbatim within the test's edit budget, and nothing else | text |
| `no_excess_repeats` | no passage of 16 words is repeated more often than the page prints its words | text |
| `present` with `{"absent": true}` | a known wrong reading (text under a redaction, the next page's first line) is not in the output | text |
| `table_cell` | this cell sits under these headings and beside these neighbors | tables |
| `layout_kind` | the block holding this line is a heading, text or table | layout |
| `layout_absent` | no block on the page is a heading, table or another listed kind (a blank page) | layout |
| `format` | this span of text is bold, italic, underlined, struck through, superscript or subscript, and the words around it are not (reported beside the headline) | format |

Tags (`handwriting`, `math`, `table`, `rotated`, script and language codes, and more) never decide a verdict; they only slice results. A failed page counts with all its tests failed.

Limits: OPB measures recall of tested claims, it is English-heavy, and it has no multi-page structure. See [docs/design.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/design.md).

## Quickstart

```bash
uv pip install omni-parse-bench                 # the scorer, and grading a dataset folder on disk
uv pip install 'omni-parse-bench[harness]'      # + the adapters, to get predictions
uv pip install 'omni-parse-bench[benchmark]'    # + the Hugging Face client, to download our dataset
```

A run is one system on one dataset: plan (checked before any call), predict (answers saved in the run's folder), grade
(score the saved answers, free to repeat). `opb init` writes a config for a registered system, and `opb systems` lists them:

```bash
export DATALAB_API_KEY=...
opb init datalab > datalab.yaml
opb run --config datalab.yaml --set rows.sample=5 --out runs/   # shows the plan, asks before calling
opb grade runs/<run>                                            # again, for free
```

Open models have a folder that serves them on any GPU host. More on runs, resuming, serving and the run folder: [docs/running.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/running.md).

## Use the scorer in code

The scorer works on its own, with no dataset and no network. One test, one verdict:

```python
from omni_parse_bench.scorers import unit_tests

tests = unit_tests.tests.parse("example-p1", {"tests": [{
    "id": "t1", "test_type": "present", "output_type": "html", "derivation": "text_layer",
    "tags": ["Latn", "eng"],
    "args": {"content": {"text": "Quarterly revenue rose 12%", "max_diffs": 1}},
    "settings": {},
}]})
unit_tests.score({"html": "<p>Quarterly revenue rose 12% on the year.</p>"}, tests)
# [Verdict(id='t1', result='pass', why='')]
```

A verdict is `pass` or `fail`, with `why` saying what went wrong. The API reference is [docs/API.md](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md).

## Docs

- [API](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md): the scorer, harness and dataset in code
- [Providers](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md): each system's settings and how open models are served
- [Scoring reference](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/scoring/README.md): what each test reads, ignores and penalizes
- [Metamorphic certificate](https://github.com/datalab-to/omni_parse_bench/blob/main/tests/metamorphic/README.md): the scorer's own checks and the deviations that remain
- [Building tests](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/building-tests.md) and [design](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/design.md)
- [Running and grading](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/running.md) and [leaderboard details](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/leaderboard.md)
- [Release notes](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/release-notes/v1.8.0.md) and [CHANGELOG](https://github.com/datalab-to/omni_parse_bench/blob/main/CHANGELOG.md)

## Contribute or dispute a test

To add a system, fix a test or dispute a verdict, open an issue or a pull request; [CONTRIBUTING.md](https://github.com/datalab-to/omni_parse_bench/blob/main/CONTRIBUTING.md) says how. A dispute names the test id and the release.


