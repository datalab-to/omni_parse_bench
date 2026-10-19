"""Omni Parse Bench: the parse task (`task.Parse`) on a dataset, graded by its unit tests (`UnitTests`).

The loop (planning, predicting, resuming, grading) is the core's, `omni_bench_core.benchmark.Benchmark`.
"""
from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from omni_bench_core import benchmark as core

from omni_parse_bench import data, errors, task, vocab
from omni_parse_bench.scorers.unit_tests import UnitTests


def default(dataset: str | Path = data.DEFAULT_DATASET, manifest: str = data.MANIFEST,
            outputs: Sequence[str] = vocab.OUTPUT_TYPES) -> core.Benchmark:
    """Omni Parse Bench on `dataset`'s `manifest`, asking for and grading `outputs`.

    Its parameters are the benchmark's options, and nothing else: `outputs` is both the task's and the
    scorer's, which must agree. Another task or other scorers make another benchmark, built directly:
    `omni_bench_core.benchmark.Benchmark(task.Parse(), dataset, [UnitTests(), ...])`.

    from omni_parse_bench import benchmark
    from omni_parse_bench.harness.providers import datalab

    b = benchmark.default()                                   # the published dataset, every output graded
    b.run([datalab.Datalab(mode="accurate")], out="runs", sample=20)
    b.grade("mine/")                                          # a folder of your own predictions
    """
    if isinstance(outputs, str): raise TypeError(f"outputs is a list of output types, not {outputs!r}")
    outputs = tuple(sorted(outputs))
    if not outputs or not set(outputs) <= set(vocab.OUTPUT_TYPES):
        raise errors.UsageError(f"outputs is a non-empty list of output types from "
                                f"{list(vocab.OUTPUT_TYPES)}, not {list(outputs)}")
    return core.Benchmark(task.Parse(outputs), dataset, [UnitTests(outputs)], manifest)

