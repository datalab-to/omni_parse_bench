"""The published dataset's invariants. Needs a dataset: set OPB_DATASET to its root.

    OPB_DATASET=~/parse_bench/dataset-v2 pytest tests/test_dataset.py

`gold.load` already checks every manifest row and test, unique ids, stray gold files and every
page's tests; this checks what only the folder can say: that it loads, and that pages/ holds each
page's file and nothing else.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from omni_parse_bench import gold

ROOT = Path(os.environ.get("OPB_DATASET", "")).expanduser()
pytestmark = pytest.mark.skipif(not (ROOT / gold.MANIFEST).exists(),
                                reason="set OPB_DATASET to a dataset root")


@pytest.fixture(scope="module")
def dataset() -> tuple[tuple[gold.Page, ...], tuple[gold.Test, ...]]:
    return gold.load(ROOT)


def test_the_dataset_loads(dataset):
    pages, tests = dataset
    assert pages and tests


def test_pages_holds_each_page_file_and_nothing_else(dataset):
    pages, _ = dataset
    assert {p.doc_path for p in pages} == {f"pages/{f.name}" for f in (ROOT / "pages").iterdir()}
