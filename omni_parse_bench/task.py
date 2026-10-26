"""The parse task: `Parse`, and `Input`, what a system is sent: a document. It imports nothing of the
harness.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import ClassVar, NamedTuple

from omni_bench_core import task

from omni_parse_bench import data


class Input(NamedTuple):
    """What a system is sent: a document (a PDF of any number of pages, or an image), and the outputs wanted
    from it. A row of the benchmark is one page, a document of one page."""

    doc: Path
    wants: frozenset[str]


@dataclasses.dataclass(frozen=True)
class Parse(task.Task[data.Page, Input]):
    """A document goes in, one page per row, and its pages' outputs come out, the ones its tests read (html,
    layout blocks): `{"pages": [...]}`. The adapter asks its system only for those it can produce
    (`harness.Parser.SUPPORTS`); a test on another output fails."""

    name: ClassVar[str] = "parse"

    def rows(self, dataset: str | Path, manifest: str = data.MANIFEST) -> tuple[data.Page, ...]:
        return data.read_manifest(dataset, manifest)[1]

    def input(self, row: data.Page) -> Input:
        """The page file and the outputs its tests read. Raises `FileNotFoundError` when the file is
        missing."""
        if not row.doc_path.is_file(): raise FileNotFoundError(f"no page file at {row.doc_path}")
        return Input(row.doc_path, frozenset(row.outputs))
