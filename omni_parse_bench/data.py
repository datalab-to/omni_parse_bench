"""The dataset: its pages, read from a folder or downloaded from Hugging Face.

`Page` is one row of the manifest, and `read_manifest` reads them all, with opb's checks on top of the
core's (`omni_bench_core.data`). Checking every test of a dataset is the scorer's, `unit_tests.check(pages)`.
"""
from __future__ import annotations

import dataclasses
import functools
from pathlib import Path
from typing import Any

from omni_bench_core import data as core

from omni_parse_bench import errors, vocab

DEFAULT_DATASET = "hf://datasets/datalab-to/omni_parse_bench"
MANIFEST = core.MANIFEST
COLUMNS = ("document", "outputs")       # what opb's rows hold besides the core's
OUTPUTS = frozenset(vocab.READS.values())     # the output types a test can read: html, blocks


class ManifestError(errors.UsageError):
    """A manifest, or a row of one, that breaks the dataset's rules. The message names it and the fix."""


@dataclasses.dataclass(frozen=True)
class Page:
    """One page: a row of the manifest, its paths full local paths, so a page's file and tests are read from
    the page alone.

    `extra` holds the row's other columns. omni-parse-bench reads none of them, so a dataset can carry
    columns of its own (a language, a tag, another gold) for scorers of its own. Treat it as read-only."""

    page_id: str
    document: str   # the source document: a page's tests pass or fail with its document's
    suite: str
    doc_path: Path  # the page file, a .pdf or .png
    gt_path: Path   # its tests: <dataset>/.../<page_id>.json
    outputs: tuple[str, ...]    # what to predict: the output types its tests read, sorted
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)   # the manifest's other columns

    @property
    def id(self) -> str:
        """The page's id, by the name every benchmark's rows share."""
        return self.page_id


@functools.cache
def read_manifest(dataset: str | Path, manifest: str = MANIFEST) -> tuple[Path, tuple[Page, ...]]:
    """The dataset's folder and its pages, checked, in the manifest's order. It reads the manifest alone: no
    gold file is opened.

    A dataset folder holds:

        manifest.parquet       a row per page: page_id, document, suite, doc_path, gt_path, outputs
        pages/...              the page files that get sent: one-page PDFs, or .png for image pages
        gold/<page_id>.json    each page's tests: {"tests": [...]}, read by the scorer (`scorers.unit_tests`)

    Downloading, and the checks every benchmark shares (ids, suites, paths inside the dataset, the gold named
    `<page_id>.json`), are the core's. opb adds three checks:

    - a page names its source `document`, a non-empty string;
    - its file is a .pdf or a .png; and
    - its `outputs` are the output types its tests read, a non-empty list of distinct names.

    It reads each manifest once per process.
    """
    root, rows = core.read_manifest(dataset, manifest, columns=COLUMNS, id="page_id", inputs=("doc_path",),
                                    gold="gt_path")
    return root, tuple(page(r) for r in rows)


def page(r: dict[str, Any]) -> Page:
    """One row the core has read and checked, with opb's own checks."""
    where = f"page {r['page_id']!r}"
    if not (isinstance(r["document"], str) and r["document"].strip()):
        raise ManifestError(f"{where}: document must be a non-empty string, not {r['document']!r}")
    if r["doc_path"].suffix not in (".pdf", ".png"):
        raise ManifestError(f"{where}: doc_path must be a .pdf or .png, not {r['doc_path'].name}")
    outputs = r["outputs"]
    if (not isinstance(outputs, list | tuple) or not outputs or not set(outputs) <= OUTPUTS
            or len(set(outputs)) != len(outputs)):
        raise ManifestError(f"{where}: outputs must be a non-empty list of distinct output types from "
                            f"{sorted(OUTPUTS)}, not {outputs!r}")
    return Page(r["page_id"], r["document"], r["suite"], r["doc_path"], r["gt_path"], tuple(sorted(outputs)),
                r["extra"])


select = core.select
download_dataset = core.download_dataset
dataset_id = core.dataset_id
