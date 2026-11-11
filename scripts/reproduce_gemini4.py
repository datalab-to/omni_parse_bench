# /// script
# requires-python = ">=3.12"
# dependencies = ["omni-parse-bench[benchmark]==1.5.0", "omni-bench-core[hub]==0.14.0"]
# ///
"""Repeat the Gemini 4 measurement protocol: original pass, then all failed pages with the bbox alias.

    uv run --script scripts/reproduce_gemini4.py google/gemini-4-argon --plan
    uv run --script scripts/reproduce_gemini4.py google/gemini-4-argon --full

Defaults to five evenly spaced pages. API calls require OPENROUTER_API_KEY and confirmation.
The stock 1.5.0 scorer is retained; only the reviewed reader function is loaded from this checkout.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path

from omni_bench_core import benchmark
from omni_parse_bench import harness, task
from omni_parse_bench.harness.providers import llm
from omni_parse_bench.scorers.unit_tests import UnitTests

DATASET = "hf://datasets/datalab-to/omni_parse_bench@d70182b9f901d1660a27e60bf6be6d6e6ea83013"


def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("model", choices=["google/gemini-4-argon", "google/gemini-4-carbon"])
    p.add_argument("--full", action="store_true", help="all 2,937 pages; otherwise five evenly spaced pages")
    p.add_argument("--plan", action="store_true", help="validate and show the selection, with no model calls")
    p.add_argument("--yes", action="store_true",
                   help="explicitly approve the original pass and its failed-page rerun")
    p.add_argument("--out", type=Path, default=Path("runs/gemini4"))
    a = p.parse_args()
    # Refuse a current editable checkout, whose scorer may differ despite its unchanged package version.
    checkout = Path(__file__).resolve().parents[1]
    if Path(llm.__file__).resolve().is_relative_to(checkout):
        p.error("run with `uv run --script`, so the published 1.5.0 scorer is used")
    if llm.as_blocks('{"type":"text","bbox":[100,200,400,700],"text":"a"}') is not None:
        p.error("the initial reader already accepts bbox; use the script's pinned 1.5.0 environment")
    s = UnitTests()
    b = benchmark.Benchmark(task.Parse(), DATASET, [s])
    system = harness.system(a.model, {})
    first = b.plan(system, a.out / "initial", sample=0 if a.full else 5, timeout=900, workers=32,
                   launch={"protocol": "original 1.5.0 pass, then every failure with the generic bbox alias"})
    print(f"{a.model}: {len(first.rows)} pages; default reasoning, max 32000 tokens, 32 page workers")
    if a.plan:
        return
    prompt = "Approve paid calls for this pass and one failed-page rerun? [y/N] "
    approved = a.yes or input(prompt).lower() == "y"
    if not approved:
        return
    b.predict(first)
    original = b.grade(first.run)
    before = lines(first.run.folder / "unit_tests/scores.jsonl")
    failed = [x["id"] for x in before if x["status"] == "failed"]
    result = {"initial": original, "failed_page_rerun": None,
              "full_summary": original["scorers"]["unit_tests"]}
    if failed:
        source = checkout / "omni_parse_bench/harness/providers/llm.py"
        text = source.read_text()
        function = next(n for n in ast.parse(text).body
                        if isinstance(n, ast.FunctionDef) and n.name == "as_blocks")
        digest = hashlib.sha256(ast.get_source_segment(text, function).encode()).hexdigest()
        exec(compile(ast.Module(body=[function], type_ignores=[]), str(source), "exec"), vars(llm))
        probe = '{"type":"text","bbox":[100,200,400,700],"text":"a"}'
        assert llm.as_blocks(probe)[0]["bbox"] == [.2, .1, .7, .4]
        retry = b.plan(system, a.out / "failed-page-rerun", only=failed, timeout=900, workers=32,
                       launch={"initial_run": first.run.name, "reader_function_sha256": digest})
        b.predict(retry)
        result["failed_page_rerun"] = b.grade(retry.run)
        after = {x["id"]: x for x in lines(retry.run.folder / "unit_tests/scores.jsonl")}
        assert set(after) == set(failed)
        combined = [after.get(x["id"], x) for x in before]
        result["full_summary"] = s._framed(s.summarize(combined), combined, first.run.name + "-after-retry")
    output = a.out / f"{first.run.name}-summary.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
