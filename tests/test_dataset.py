"""The published dataset's invariants. Needs a dataset: set OPB_DATASET to its root.

    OPB_DATASET=~/parse_bench/dataset-v2 pytest tests/test_dataset.py

`unit_tests.check` already checks every manifest row and test, unique ids, and every
page's tests; this checks what only the folder can say: that it loads, and that pages/ holds each
page's file and nothing else.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omni_parse_bench import data
from omni_parse_bench.scorers.unit_tests import tests as gold
from omni_parse_bench.scorers import unit_tests as scorer

ROOT = Path(os.environ.get("OPB_DATASET", "")).expanduser()
pytestmark = pytest.mark.skipif(not (ROOT / data.MANIFEST).exists(),
                                reason="set OPB_DATASET to a dataset root")


@pytest.fixture(scope="module")
def dataset() -> tuple[tuple[data.Page, ...], tuple[gold.Test, ...]]:
    _, pages = data.read_manifest(ROOT)
    return pages, scorer.check(pages)


def test_the_dataset_loads(dataset):
    pages, tests = dataset
    assert pages and tests


def test_pages_holds_each_page_file_and_nothing_else(dataset):
    pages, _ = dataset
    assert {p.doc_path for p in pages} == set((ROOT.resolve() / "pages").iterdir())
