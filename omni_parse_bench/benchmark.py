"""Omni Parse Bench: the parse task (`task.Parse`) on a dataset, graded by its unit tests (`UnitTests`).

The loop (planning, predicting, resuming, grading) is the core's, `omni_bench_core.benchmark.Benchmark`.
"""
from __future__ import annotations

from pathlib import Path

from omni_bench_core import benchmark as core

from omni_parse_bench import data, task
from omni_parse_bench.scorers.unit_tests import UnitTests


def default(dataset: str | Path = data.DEFAULT_DATASET, manifest: str = data.MANIFEST) -> core.Benchmark:
    """Omni Parse Bench on `dataset`'s `manifest`: each page asks for the outputs its tests read, and every
    test is graded.

    Its parameters are the benchmark's options, and nothing else. Another task or other scorers make another
    benchmark, built directly: `omni_bench_core.benchmark.Benchmark(task.Parse(), dataset, [UnitTests(),
    ...])`.

        from omni_parse_bench import benchmark
        from omni_parse_bench.harness.providers import datalab

        if __name__ == "__main__":
            b = benchmark.default()                               # the published dataset
            b.run(datalab.Datalab(mode="accurate"), out="runs", sample=20)
            b.grade("mine/")                                      # a folder of your own predictions
    """
    return core.Benchmark(task.Parse(), dataset, [UnitTests()], manifest)
