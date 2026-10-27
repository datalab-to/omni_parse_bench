# Omni Parse Bench

[![test](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml/badge.svg)](https://github.com/datalab-to/omni_parse_bench/actions/workflows/test.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/pyproject.toml)
[![Code: Apache 2.0](https://img.shields.io/badge/code-Apache%202.0-blue)](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE)
[![Data: per source](https://img.shields.io/badge/data-per%20source-lightgrey)](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses)
[![Dataset on Hugging Face](https://img.shields.io/badge/%F0%9F%A4%97%20dataset-omni__parse__bench-yellow)](https://huggingface.co/datasets/datalab-to/omni_parse_bench)

This repository contains a way to benchmark document-parsing systems using our unit-test scorer and dataset as well as your own. Concretely, this repository holds:

- the scorer, which works on its own: a page's output and its tests as input, a verdict per test as output;
- the benchmark: run over our dataset on [Hugging Face](https://huggingface.co/datasets/datalab-to/omni_parse_bench), or
  your own; and
- the systems: different registered systems that you can easily evaluate, including open models with a folder to serve each on a GPU.

Contents:

1. [How scoring works](#how-scoring-works): tests, families, the headline and tags;
2. [Install](#install): the scorer alone, or with the adapters and the dataset;
3. [Run the benchmark](#run-the-benchmark): one system on the dataset, from a config;
4. [Grade](#grade): a run again, or predictions of your own;
5. [Score on your own](#score-on-your-own): the scorer on its own, in code or from the command line;
6. [Predict one page](#predict-one-page): one page through one system;
7. [Results](#results): every system we ran on the published dataset;
8. [License](#license); and
9. [Citation](#citation).

## How scoring works

![The benchmark's design: headline, families, tests, args and tags](https://raw.githubusercontent.com/datalab-to/omni_parse_bench/main/docs/assets/design.svg)

A test is a yes/no question about one page. Each test type belongs to one of three families:

| test type | checks | family |
|---|---|---|
| `present` | this text, number or equation appears | text |
| `order` | text A comes before text B | text |
| `repeat` | this line appears exactly N times | text |
| `table_cell` | this cell sits under these headings and beside these neighbors | tables |
| `layout_kind` | the block holding this line is a heading, text or table | layout |

A family's score is the share of its tests that pass, and the headline is the mean of the three family scores.

Each test is tagged by what it checks:

- structure: `table`, `math`, `form` and `multi_column`;
- rendering: `handwriting`, `tiny`, `rotated` and `degraded`;
- role: `heading`, `caption`, `footnote`, `list`, `code`, `figure` and `header_footer`;
- script: ISO 15924 codes (`Latn`, `Hani`, `Deva`, ...); and
- language: ISO 639-3 codes (`eng`, `fra`, `tha`, ...).

Tags never decide whether a test passes, or the headline. They are only for slicing the results, such as the score
on handwriting alone. The full design is [`docs/design.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/design.md).

## Install

```bash
uv pip install omni-parse-bench                 # the scorer, and grading a dataset folder on disk
uv pip install 'omni-parse-bench[harness]'      # + the adapters, to get predictions
uv pip install 'omni-parse-bench[benchmark]'    # + the Hugging Face client, to download our dataset
```

## Run the benchmark

A run is one system on one dataset. It works in three stages:

1. Plan: check the config, the system's keys and the dataset's files before any call;
2. Predict: send each page to the system and save each answer in the run's folder; and
3. Grade: score the saved answers. Grading calls no system, so it can be done again for free.

### A config

A run is one config: a YAML file with every key written out. `opb init` writes one for a registered system, every
option at its default, and on our dataset:

```bash
opb init datalab > datalab.yaml
```

```yaml
dataset: hf://datasets/datalab-to/omni_parse_bench   # a folder, or a Hugging Face dataset
manifest: manifest.parquet                           # which of its pages, with which files
scorers:
  unit_tests: {}
rows:
  sample: 0
  limit: 0
  only: null
timeout: 900.0           # seconds
workers: 0               # pages in flight at once; 0 for the system's default
system:
  datalab:
    mode: accurate
    ...
```

`opb systems` lists every system you can run; `opb systems <name>` shows its options and the key it needs.

`--set path=value` changes one value the file has, read as YAML, and refuses a path it hasn't. This runs Datalab
on 5 pages:

```bash
export DATALAB_API_KEY=...
opb run --config datalab.yaml --set rows.sample=5 --out runs/
```

`opb run` shows the plan and asks before calling any system.

### Models you serve

Each open model has a folder, `omni_parse_bench/harness/providers/serve/<model>/`, that serves it on any GPU host:

```bash
docker build -t opb-chandra-ocr omni_parse_bench/harness/providers/serve/chandra-ocr
docker run --gpus all -p 8001:8001 opb-chandra-ocr
opb init chandra-ocr > chandra.yaml
opb run --config chandra.yaml --set system.chandra-ocr.base_url=http://<host>:8001
```

The system's `served` option names the weights and their revision. Before any call, opb asks the server what it
serves, and refuses a run whose server serves something else.
[`docs/providers.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/providers.md#serving-an-open-model)
has more information.

### Run folder shape

```
runs/datalab-20261026-185915-9c9e/
  config.yaml                         # resolved config; point to this to rerun
  settings.json                       # the question it answers and the launch; resume checks against it
  server.json                         # for a model you serve: what its server said it serves
  records/<id>.json                   # response from the system in full (cost, raw response)
  predictions/<id>.json               # prediction portion of the response
  unit_tests/summary.json             # summary of scores
  unit_tests/scores.jsonl             # scores (line-per-page)
  unit_tests/details/<id>.jsonl       # detailed info (verdict per test) per page
```

[`docs/API.md`](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md) has more information,
including [how to run on your own dataset](https://github.com/datalab-to/omni_parse_bench/blob/main/docs/API.md#the-dataset).

### Resume

You can resume a run by giving a path to its folder.

```bash
opb resume runs/<run>                                         # continue where it stopped
opb resume runs/<run> --retry-failed                          # also ask again for timeouts, etc.
opb resume runs/<run> --retry-failed --set timeout=1800       # increase timeout
```

## Grade

`opb run` grades its run when it finishes. To grade a run again, or a folder of your own predictions:

```bash
opb grade runs/datalab-20261021-160012-3f9a        # a run knows its own dataset
opb grade mine/ --dataset my-dataset/              # your predictions on your own dataset
```

A summary looks like this:

```json
{
  "scorer": "unit_tests",
  "run": "datalab-20261021-160012-3f9a",
  "headline": 0.648,
  "headline_is": "scored.headline × coverage",
  "rows": 5,
  "failed": 1,
  "coverage": 0.8,
  "scored": {
    "headline": 0.81,
    "headline_is": "the mean of the families' scores",
    "families": {
      "text": {"score": 0.9, "tests": 96, "documents": 4},
      "tables": {"score": 0.74, "tests": 32, "documents": 2},
      "layout": {"score": 0.79, "tests": 24, "documents": 4}
    }
  }
}
```

## Score on your own

The scorer works on its own, with no dataset and no network. Here is one page with three tests:

```python
from omni_parse_bench import data
from omni_parse_bench.scorers import unit_tests

tests = unit_tests.tests.parse("example-p1", {"tests": [
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

pred = {
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
verdicts = unit_tests.score(pred, tests)
```

```python
>>> verdicts
[Verdict(id='t1', result='pass', why=''),
 Verdict(id='t2', result='pass', why=''),
 Verdict(id='t3', result='fail', why="no cell matching '4.2' in any table")]

>>> page = data.Page("example-p1", "example", "example", "pages/example-p1.pdf", "gold/example-p1.json", ("html",))
>>> lines = unit_tests.lines(verdicts, tests, page)
>>> unit_tests.summarize(lines)
{'headline': 0.5, 'families': {'text': {'score': 1.0, 'tests': 2, 'documents': 1},
                               'tables': {'score': 0.0, 'tests': 1, 'documents': 1}}}
>>> unit_tests.summarize([x for x in lines if "table" in x["tags"]])   # one tag: the same summary on a slice
{'headline': 0.0, 'families': {'tables': {'score': 0.0, 'tests': 1, 'documents': 1}}}
```

A verdict is `pass` or `fail`, with `why` saying what went wrong.

The same from the command line, which prints the verdicts:

```bash
opb score --pred outputs.json --gold gold/<page_id>.json
```

## Predict one page

With `[harness]` installed, each system is an adapter class. `harness.system` makes one from a system name and its
options and `harness.predict` sends one page under the same rules a run uses (one time budget, retries, failures
recorded) and returns its record:

```python
from pathlib import Path

from omni_parse_bench import harness
from omni_parse_bench.scorers import unit_tests

datalab = harness.system("datalab", {"mode": "accurate"})
record = harness.predict(datalab, harness.Input(Path("pages/<page_id>.pdf"), frozenset({"html", "blocks"})))
record["output"]    # {"pages": [{"html": "...", "blocks": [...]}]}
record["raw"]       # the answer as the system gave it
record["cost"]      # what it cost, its wall time and attempts

unit_tests.score(record["output"]["pages"][0], unit_tests.tests.read("gold/<page_id>.json"))   # one page's outputs
```

```bash
opb predict --system datalab --page pages/<page_id>.pdf --options '{"mode": "accurate"}'
```

## Results

Every system on our dataset.

| parser | weights | parameters | headline | text | tables | layout | refusals |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Datalab accurate | closed |  | 94.1 | 92.0 | 94.2 | 96.0 | — |
| Gemini 3.8 Flash * | closed |  | 92.7 | 91.9 | 95.3 | 92.9 | 8 |
| Datalab balanced | closed |  | 92.6 | 90.1 | 91.6 | 96.2 | — |
| GPT-6.1 Sol | closed |  | 91.4 | 90.7 | 95.6 | 89.5 | 17 |
| Reducto | closed |  | 90.8 | 85.4 | 91.2 | 95.8 | — |
| Claude Opus 5.5 | closed |  | 90.7 | 94.5 | 97.2 | 84.3 | 40 |
| LlamaParse | closed |  | 90.4 | 88.2 | 92.6 | 90.4 | — |
| chandra-ocr-2 (Datalab) | open | 4.5B | 90.1 | 87.4 | 87.4 | 95.4 | — |
| Mistral OCR | closed |  | 89.5 | 82.8 | 91.9 | 93.8 | — |
| Claude Sonnet 5.5 * | closed |  | 88.7 | 93.3 | 96.1 | 77.5 | 7 |
| dots.mocr | open | 3.0B | 87.9 | 82.5 | 88.6 | 92.5 | — |
| GPT-5.6 Sol | closed |  | 87.7 | 86.2 | 91.6 | 86.9 | 17 |
| MinerU2.5-Pro | open | 1.2B | 87.1 | 77.4 | 92.1 | 91.7 | — |
| Infinity-Parser2-Pro | open | 35.1B (MoE) | 87.0 | 83.3 | 84.1 | 93.5 | — |
| Extend | closed |  | 83.3 | 64.1 | 92.5 | 93.4 | — |
| Surya OCR 2 (Datalab) | open | 0.67B | 83.1 | 80.6 | 74.3 | 94.3 | — |
| Azure | closed |  | 83.0 | 74.6 | 81.7 | 92.8 | — |
| LightOnOCR-3-4B | open | 4.5B | 82.9 | 83.9 | 70.8 | 94.0 | — |
| LightOnOCR-3-0.8B | open | 0.85B | 81.6 | 81.1 | 72.1 | 91.7 | — |
| GLM-OCR | open | 1.3B | 81.5 | 71.0 | 84.2 | 89.3 | — |
| Nemotron 3.5 Parse | open | 0.63B | 80.0 | 72.4 | 77.3 | 90.2 | — |
| Unlimited-OCR | open | 3.3B | 79.3 | 70.2 | 76.5 | 91.1 | — |
| PaddleOCR-VL-1.6 | open | 0.96B | 78.7 | 61.7 | 83.7 | 90.7 | — |
| Infinity-Parser2-Flash | open | 2.2B | 78.4 | 78.4 | 66.5 | 90.4 | — |
| DeepSeek-OCR-2 | open | 3.4B | 75.2 | 64.2 | 70.0 | 91.4 | — |
| Indra OCR (Datalab) | open | about 12M † | 69.5 | 60.3 | 58.1 | 90.1 | — |
| HunyuanOCR-1.5 | open | 1.0B | 64.6 | 50.5 | 61.9 | 81.4 | — |
| olmOCR-2 | open | 8.3B | none | 71.3 | 56.6 | unsupported | — |
| Nanonets-OCR2-3B | open | 3.8B | none | 68.2 | 62.6 | unsupported | — |
| Tesseract | open | n/a | none | 17.6 | 0.0 | unsupported | — |

\* Used in creating and verifying at least some tests. † See [`docs/results.md`](./docs/results.md). A system with
no layout blocks has no layout score, so no headline ([Grade](#grade)).

Refusals count distinct pages with at least one required output refused by the provider, including content
filtering and Gemini's `RECITATION` stop; `—` means not audited, rather than zero. The five LLM rows use the
current run rule: the mean of the family scores on answered pages, multiplied by page coverage. A failed
required request fails its page; the family columns describe answered pages only. Gemini has 8 refusals and 12
other failed pages; Sonnet 5.5 has 7 refusals and 3 other failed pages. GPT-5.6 Sol has 17 refusals; Opus 5.5
has 40; GPT-6.1 Sol has 17, with no other failed pages in those three runs.

Opus 5.5 and GPT-6.1 Sol were each run once on 2026-10-27 using omni-parse-bench 1.0.0, the stock OpenRouter
adapter and each model's default reasoning. The three earlier LLM rows were recomputed from their published
verdicts and archived failure records under the same coverage rule, without new inference or changes to the
tests. [Machine-readable LLM run summaries](docs/llm-run-summaries.json) give the exact scores, denominators
and failed/refused page IDs.

## License

The code is Apache 2.0: see [`LICENSE`](https://github.com/datalab-to/omni_parse_bench/blob/main/LICENSE), and
[`NOTICE`](https://github.com/datalab-to/omni_parse_bench/blob/main/NOTICE) for the third-party code it includes
(KaTeX, MIT; a rewrite of olmOCR-bench's table parser, Apache 2.0).

The data's licenses are per source. Each source of the pages, its license and the credit it requires are in
[`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses), one file per source. The tests
are CC BY 4.0, except those converted from olmOCR-bench (ODC-BY 1.0) and fr-bench-pdf2md (MIT), and those quoting
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

Please also cite the upstream datasets whose pages or tests this benchmark uses; they are listed in
[`licenses/`](https://github.com/datalab-to/omni_parse_bench/tree/main/licenses).
