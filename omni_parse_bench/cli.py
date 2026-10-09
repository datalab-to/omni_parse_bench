"""The `opb` command: a thin wrapper over `score`, `predict` and `benchmark`.

    opb score --pred outputs.json --gold gold/<page_id>.json
    opb predict --provider datalab --page pages/<page_id>.pdf
    opb benchmark --providers datalab openai/gpt-5.6-sol --dataset hf://datasets/datalab-to/omni_parse_bench
    opb tests --dataset <folder or hf://...> > tests.jsonl
    opb providers [NAME]
    opb reparse RUN_DIR ...

Everything goes to stdout as JSON except `benchmark`'s progress, and `benchmark` shows its plan
and waits for a yes unless given `-y`; nothing in the library ever reads stdin. `benchmark` exits 2
when a test's grading failed in our code, so a scorer bug can't pass as a vendor's score.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omni_parse_bench import benchmark



def read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise SystemExit(f"no file at {path}") from None
    except json.JSONDecodeError as e:
        raise SystemExit(f"{path} isn't JSON: {e}") from None


def read_options(value: str | None) -> dict:
    """`--options` as a dict: inline JSON, or a path to a JSON file."""
    if not value: return {}
    text = Path(value).read_text() if Path(value).exists() else value
    try:
        out = json.loads(text)
    except json.JSONDecodeError as e:
        raise SystemExit(f"--options isn't JSON: {e}") from None
    if not isinstance(out, dict):
        raise SystemExit(f"--options must be a JSON object, got {type(out).__name__}")
    return out


def cmd_score(a: argparse.Namespace) -> int:
    """What `score` returns: one verdict per test of the page."""
    from omni_parse_bench import gold, score

    if not Path(a.gold).exists(): raise SystemExit(f"no file at {a.gold}")
    vs = score(read_json(a.pred), gold.read(a.gold), unsupported=set(a.unsupported or ()))
    print(json.dumps([v._asdict() for v in vs], indent=2, ensure_ascii=False))
    return 0


def cmd_tests(a: argparse.Namespace) -> int:
    """Every test of a dataset as a JSON line, with its page's id, suite and document: a flat table
    to query (polars, DuckDB, pandas), made from the gold files and never stored."""
    from omni_parse_bench import gold

    root = benchmark.dataset_root(a.dataset)
    pages, _ = gold.load(root)   # Note: loaded first, so only a dataset that checks is written out.
    for p in pages:
        for t in json.loads((root / p.gt_path).read_text())["tests"]:
            row = {"id": t["id"], "page_id": p.page_id, "suite": p.suite, "document": p.document} | t
            print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    from omni_parse_bench import harness

    record = harness.predict(a.provider, a.page, set(a.wants) if a.wants else None, timeout=a.timeout,
                             **read_options(a.options))
    if not a.raw: record.pop("raw")
    print(json.dumps(record, indent=2, ensure_ascii=False))
    return 0 if not any(v != "unsupported" for v in record["errors"].values()) else 1


EXAMPLE_MODELS = ("openai/gpt-5.6-sol",)


def cmd_providers(a: argparse.Namespace) -> int:
    """Every provider, or one provider's options, as a table in a terminal and a list in a pipe.

    The options come from the adapter's own `Config` (its fields are the options and their
    defaults), so this can't drift from what the adapter accepts.
    """
    from rich import box
    from rich.console import Console
    from rich.table import Table

    from omni_parse_bench import harness
    from omni_parse_bench.harness import registry

    console = Console()
    if not a.provider:
        if not console.is_terminal:
            for name in (*harness.PROVIDERS, *EXAMPLE_MODELS): print(name)
            return 0
        table = Table(box=box.SIMPLE_HEAD, pad_edge=False, show_edge=False)
        table.add_column("provider")
        table.add_column("outputs")
        for name in harness.PROVIDERS:
            table.add_row(name, ", ".join(sorted(harness.adapter(name).SUPPORTS)))
        table.add_section()
        for name in EXAMPLE_MODELS:
            table.add_row(name, ", ".join(sorted(harness.adapter(name).SUPPORTS)))
        console.print(table)
        print("\nmodel ids are examples: any OpenRouter org/model id works.")
        return 0
    config = registry.config_for(a.provider)
    table = Table(box=box.SIMPLE_HEAD, pad_edge=False, show_edge=False, title=a.provider,
                  title_justify="left")
    table.add_column("option")
    table.add_column("default", overflow="fold")
    table.add_column("", style="dim", overflow="fold")
    for f in dataclasses.fields(config):
        value = getattr(config, f.name)
        table.add_row(f.name, "''" if value == "" else str(value), f.metadata.get("help", ""))
    console.print(table)
    first = next((f.name for f in dataclasses.fields(config) if f.name != "model"), None)
    if first:
        options = json.dumps({a.provider: {first: "..."}})
        print(f"\nopb benchmark --providers {a.provider} --options '{options}'")
    return 0


def confirm_plan(plan: Any) -> bool:
    """Show what the benchmark is about to do, and ask. `-y` / `--yes` skips this entirely.

    A run costs money, so the default is to say what it will do before it starts. The plan goes
    to stderr with the rest of the progress, leaving stdout for the scores.

    Nobody to ask is not the same as no: a pipe, a cron job or a CI step has no terminal, so it
    proceeds, since it was scripted, which is consent. Only an interactive session is asked.
    """
    from rich.console import Console

    Console(stderr=True, highlight=False).print(benchmark.plan_view(plan))
    if not sys.stdin.isatty():
        return True
    try:
        return input("  proceed? [y/N] ").strip().lower() in ("y", "yes")
    except EOFError:
        return False


def cmd_benchmark(a: argparse.Namespace) -> int:
    import logging

    # Note: with no terminal, progress comes out as log lines; they go to stderr with the plan.
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)
    # Note: the HTTP clients log every request at INFO, which would scroll the table away;
    # huggingface_hub 2 makes its requests through httpx2, whose logger is its own.
    for name in ("httpx", "httpx2", "httpcore", "openai", "huggingface_hub"):
        logging.getLogger(name).setLevel(logging.WARNING)
    try:
        p = benchmark.plan(a.providers, out=a.out, dataset=a.dataset, suites=a.suites, limit=a.limit,
                           sample=a.sample, options=read_options(a.options), timeout=a.timeout,
                           workers=a.workers, rescore=a.rescore, score_only=a.score_only,
                           retry_failed=a.retry_failed,
                           only=frozenset(a.pages.read_text().split()) if a.pages else None)
    except ValueError as exc:
        raise SystemExit(f"opb benchmark: {exc}") from None
    if not a.yes and not a.score_only and not confirm_plan(p):
        return 1
    summaries = benchmark.execute(p, lambda s: print(s, file=sys.stderr))
    # Note: the coverage beside the scores, since a run with pages pending is scored on fewer pages.
    print(json.dumps({k: {**{o: v["score"] for o, v in s.items() if isinstance(v, dict) and "score" in v},
                          "pages": s["pages"], "pages_pending": s["pages_pending"]}
                      for k, s in summaries.items()}, indent=2))
    if errored := {k: n for k, s in summaries.items() if (n := benchmark.errors_in(s))}:
        print(f"warning: grading failed in our code (not the vendor's) for {sum(errored.values())} tests: "
              + ", ".join(f"{k} {n}" for k, n in errored.items())
              + ". They are left out of the scores; report it with the run's scores.jsonl.", file=sys.stderr)
        return 2
    return 0


def cmd_reparse(a: argparse.Namespace) -> int:
    """Read each record's outputs again from its saved answers, with the current adapter code.

    Nothing is paid: a parsing fix reaches a finished run this way. With `--add`, outputs the run
    never asked for are read from its answers too, where they hold them (`harness.reparse`). The run's
    scores are then out of date, so grade it again with `opb benchmark ... --score-only --rescore`.
    """
    from omni_parse_bench import harness

    for run in a.runs:
        changed = total = 0
        for path in sorted((run / "records").glob("*.json")):
            record = json.loads(path.read_text())
            new = harness.reparse(record, frozenset(a.add or ()))
            total += 1
            if new["outputs"] == record["outputs"] and new["errors"] == record["errors"]: continue
            changed += 1
            benchmark.write_json(path, new)
            benchmark.write_json(run / "predictions" / path.name, new["outputs"])
        print(f"{run}: {changed} of {total} records changed", file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="opb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="grade one page's outputs against its tests: one verdict per test")
    s.add_argument("--pred", required=True, help="the outputs, JSON: {output type: value}")
    s.add_argument("--gold", required=True, help="the page's gold file, gold/<page_id>.json")
    s.add_argument("--unsupported", nargs="*", metavar="OUTPUT",
                   help="output types the provider can't produce")

    d = sub.add_parser("predict", help="run one page through one provider")
    d.add_argument("--provider", required=True, help="a vendor (opb providers), or an OpenRouter model id")
    d.add_argument("--page", required=True, help="the page, .pdf or .png")
    d.add_argument("--wants", nargs="*", metavar="OUTPUT",
                   help="output types to produce (default: all it supports)")
    d.add_argument("--timeout", type=float, default=900, help="seconds per vendor call")
    d.add_argument("--options", metavar="JSON", help="the provider's options, inline JSON or a file")
    d.add_argument("--raw", action="store_true", help="also print the vendor's raw responses")

    b = sub.add_parser("benchmark", help="predict and score every page, resumably")
    b.add_argument("--providers", nargs="+", required=True, metavar="NAME")
    b.add_argument("--dataset", default=benchmark.DEFAULT_DATASET,
                   help="a dataset folder, or hf://datasets/<repo>[@revision]")
    b.add_argument("--out", type=Path, default=Path("runs"), help="where run directories go")
    b.add_argument("--suites", nargs="+", help="limit to these suites")
    b.add_argument("--limit", type=int, default=0, help="first N pages")
    b.add_argument("--sample", type=int, default=0, help="N pages spread over every suite; for a smoke test")
    b.add_argument("--pages", type=Path, help="a file of page ids, one per line: run only these pages")
    b.add_argument("--options", metavar="JSON",
                   help='per provider: {"datalab": {"mode": "balanced"}}, or a list of such dicts '
                        "for several runs")
    b.add_argument("--timeout", type=float, default=900, help="seconds per vendor call")
    b.add_argument("--workers", type=int, default=0,
                   help="calls at once per adapter, shared by its runs (default: a table per vendor)")
    b.add_argument("--rescore", action="store_true", help="grade every page again, after a scorer change")
    b.add_argument("--score-only", action="store_true", help="grade what's recorded; predict nothing")
    b.add_argument("--retry-failed", action="store_true",
                   help="predict again outputs whose call may go otherwise: timeouts, outages, 429 and 5xx; "
                        "never a 400 or a vendor's answer")
    b.add_argument("-y", "--yes", action="store_true", help="don't ask before calling vendors")

    tt = sub.add_parser("tests", help="every test as a JSON line, with its page's suite and document")
    tt.add_argument("--dataset", default=benchmark.DEFAULT_DATASET,
                    help="a dataset folder, or hf://datasets/<repo>[@revision]")

    rp = sub.add_parser("reparse", help="read outputs again from saved answers, after a parsing fix")
    rp.add_argument("runs", nargs="+", type=Path, metavar="RUN_DIR")
    rp.add_argument("--add", nargs="+", metavar="OUTPUT",
                    help="also read these outputs from the saved answers")

    pl = sub.add_parser("providers", help="list the providers and their options")
    pl.add_argument("provider", nargs="?")

    a = ap.parse_args(argv)
    return {"score": cmd_score, "predict": cmd_predict, "benchmark": cmd_benchmark, "tests": cmd_tests,
            "providers": cmd_providers, "reparse": cmd_reparse}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
