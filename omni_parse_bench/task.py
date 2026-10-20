"""The parse task: `Parse`, and `Input`, what a system is sent for one page.

It imports nothing of the harness, so grading needs none of the adapters' packages.
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import ClassVar, NamedTuple

from omni_bench_core import task

from omni_parse_bench import data


class Input(NamedTuple):
    """What a system is sent for one page: the page file, and the outputs wanted from it."""

    page: Path
    wants: frozenset[str]


@dataclasses.dataclass(frozen=True)
class Parse(task.Task[data.Page, Input]):
    """The parse task: a page goes in, and the outputs its tests read come out (html, layout blocks).

    A page asks for the outputs its manifest row lists, which are the outputs its tests read. The adapter
    asks its system only for those it can produce (`harness.PageAdapter.SUPPORTS`); a test on an output the
    system can't produce fails, and the summary's families show it (html: text, tables; blocks: layout)."""

    name: ClassVar[str] = "parse"

    def rows(self, dataset: str | Path, manifest: str = data.MANIFEST) -> tuple[data.Page, ...]:
        return data.read_manifest(dataset, manifest)[1]

    def input(self, row: data.Page) -> Input:
        """The page file and the outputs its tests read. Raises `FileNotFoundError` when the file is
        missing."""
        if not row.doc_path.is_file(): raise FileNotFoundError(f"no page file at {row.doc_path}")
        return Input(row.doc_path, frozenset(row.outputs))
