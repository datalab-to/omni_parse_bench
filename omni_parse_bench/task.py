"""The parse task: a page goes in, and its html and layout blocks come out.

`Parse` also refuses, before any call, a system that can't produce an output being graded (`Parse.check`).
"""
from __future__ import annotations

import dataclasses
from collections.abc import Sequence
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import task

from omni_parse_bench import data, errors, harness, vocab
from omni_parse_bench.scorers.unit_tests import UnitTests


@dataclasses.dataclass(frozen=True)
class Parse(task.Task[data.Page, harness.Input]):
    """The parse task: a page goes in, and the outputs its tests read come out (html, layout blocks).

    `outputs` limits what is asked for: a page is asked only for the outputs it has tests for that are
    among `outputs`. So grading html alone never pays for layout blocks."""

    name: ClassVar[str] = "parse"
    outputs: tuple[str, ...] = vocab.OUTPUT_TYPES

    def rows(self, dataset: str | Path, manifest: str = data.MANIFEST) -> tuple[data.Page, ...]:
        return data.read_manifest(dataset, manifest)[1]

    def input(self, row: data.Page) -> harness.Input:
        """The page file and the outputs wanted from it. Raises `FileNotFoundError` when the file is
        missing."""
        if not row.doc_path.is_file(): raise FileNotFoundError(f"no page file at {row.doc_path}")
        return harness.Input(row.doc_path, frozenset(row.outputs) & frozenset(self.outputs))

    def check(self, systems: Sequence[harness.PageAdapter], scorers: Sequence[Any]) -> None:
        """Refuses a system that can't produce an output a `UnitTests` scorer grades: every one of those tests
        would fail, which says nothing about how it parses. Grade it on the outputs it has instead."""
        graded = {o for s in scorers if isinstance(s, UnitTests) for o in s.outputs}
        for x in systems:
            if missing := sorted(graded - x.SUPPORTS):
                can = sorted(x.SUPPORTS & graded) or sorted(x.SUPPORTS)
                raise errors.UsageError(f"{x.provider} can't produce {missing}; grade it on what it can, "
                                        f"with outputs={can}")
