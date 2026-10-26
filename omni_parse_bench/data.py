"""The dataset: `Page`, one row of the manifest, and `read_manifest`, which reads them all."""
from __future__ import annotations

import dataclasses
import functools
from pathlib import Path
from typing import Any

from omni_bench_core import data as core

from omni_parse_bench import vocab

DEFAULT_DATASET = "hf://datasets/datalab-to/omni_parse_bench"
MANIFEST = core.MANIFEST
NO_SUITE = "other"   # the suite of a page whose manifest gives none
COLUMNS = ("document", "outputs")       # what opb's rows hold besides the core's
OUTPUTS = frozenset(vocab.READS.values())     # the output types a test can read: html, blocks


@dataclasses.dataclass(frozen=True)
class Page:
    """One page: a row of the manifest, its paths full local paths. `extra` holds the row's other columns,
    which opb never reads, for scorers of your own; treat it as read-only."""

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
    """The dataset's folder and its pages, checked, in the manifest's order; no gold file is opened. A dataset
    folder holds:

        manifest.parquet       a row per page: page_id, document, doc_path, gt_path, outputs; suite optional
        pages/...              the page files sent: one-page PDFs, or .png for image pages
        gold/<page_id>.json    each page's tests: {"tests": [...]}

    On top of the core's checks (ids, paths inside the dataset, gold named `<page_id>.json`), opb checks that:

    - `document` is a non-empty string, and `suite` a string, or missing, empty or null for `NO_SUITE`;
    - the page file is a .pdf or a .png; and
    - `outputs` are the output types its tests read, a non-empty list of distinct names.

    Each manifest is read once per process."""
    root, rows = core.read_manifest(dataset, manifest, columns=COLUMNS, id="page_id", inputs=("doc_path",),
                                    gold="gt_path")
    return root, tuple(page(r) for r in rows)


def page(r: dict[str, Any]) -> Page:
    """One row the core has read and checked, with opb's own checks."""
    where = f"page {r['page_id']!r}"
    if not (isinstance(r["document"], str) and r["document"].strip()):
        raise ValueError(f"{where}: document must be a non-empty string, not {r['document']!r}")
    extra = dict(r["extra"])
    suite = extra.pop("suite", None)
    if suite is not None and not isinstance(suite, str):
        raise ValueError(f"{where}: suite must be a string, or null for {NO_SUITE!r}, not {suite!r}")
    if r["doc_path"].suffix not in (".pdf", ".png"):
        raise ValueError(f"{where}: doc_path must be a .pdf or .png, not {r['doc_path'].name}")
    outputs = r["outputs"]
    if (not isinstance(outputs, list | tuple) or not outputs or not set(outputs) <= OUTPUTS
            or len(set(outputs)) != len(outputs)):
        raise ValueError(f"{where}: outputs must be a non-empty list of distinct output types from "
                         f"{sorted(OUTPUTS)}, not {outputs!r}")
    suite = suite if (suite or "").strip() else NO_SUITE
    return Page(r["page_id"], r["document"], suite, r["doc_path"], r["gt_path"], tuple(sorted(outputs)),
                extra)
