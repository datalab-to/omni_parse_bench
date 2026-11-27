# Running and grading

The parts of the quickstart in the README, in full.

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







