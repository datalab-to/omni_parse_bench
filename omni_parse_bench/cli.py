"""The `opb` command: a thin wrapper over `benchmark.default()` and the scorer.

    opb run --providers datalab openai/gpt-5.6-sol --sample 20     # predict, then grade, resumably
    opb grade RUN_DIR                                              # a folder of predictions/, yours or a run
    opb score --pred outputs.json --gold gold/<page_id>.json       # one page's verdicts
    opb predict --provider datalab --page pages/<page_id>.pdf      # one page through one system
    opb check --dataset <folder or hf://...>                       # is the dataset one opb can run?
    opb tests --dataset <folder or hf://...> > tests.jsonl         # every test as a JSON line
    opb providers [NAME]                                           # the providers, or one's options
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omni_bench_core import run as runs

from omni_parse_bench import data, errors, vocab
from omni_parse_bench.scorers import unit_tests

EXAMPLE_MODELS = ("openai/gpt-5.6-sol",)


def deprecated(old: str, new: str) -> None:
    """Says on stderr that `old` is deprecated, and what to use instead."""
    print(f"opb: {old} is deprecated and will be removed in a later release; use {new}", file=sys.stderr)


def supported(outputs: Sequence[str] | None, unsupported: Sequence[str] | None) -> list[str] | None:
    """The outputs to grade, given the old `--unsupported`: every output, or `outputs`, but those."""
    if not unsupported: return outputs
    return [o for o in (outputs or vocab.OUTPUT_TYPES) if o not in set(unsupported)]


def read_object(path: str, flag: str) -> dict:
    """The JSON object in the file `path` that `flag` names."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise errors.UsageError(f"{flag} {path}: no such file") from None
    except IsADirectoryError:
        raise errors.UsageError(f"{flag} {path} is a folder; pass a JSON file") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise errors.UsageError(f"{flag} {path} isn't JSON: {exc}") from None
    if not isinstance(got, dict):
        kind = "null" if got is None else type(got).__name__
        raise errors.UsageError(f"{flag} {path} holds a JSON {kind}; it must be a JSON object")
    return got


def read_json(value: str | None, flag: str) -> Any:
    """A flag's JSON: inline, or a path to a JSON file."""
    if not value: return None
    is_file = Path(value).is_file()
    try:
        return json.loads(Path(value).read_text(encoding="utf-8-sig") if is_file else value)
    except json.JSONDecodeError as e:
        raise errors.UsageError(f"{flag} {value!r} is neither JSON nor a JSON file: {e}") from None


def read_ids(path: Path, flag: str) -> frozenset[str]:
    """A file of ids, one per line; blank lines and `#` comments are skipped."""
    if not path.is_file():
        raise errors.UsageError(f"{flag} {path}: no such file; it holds ids, one per line")
    return frozenset(x for line in path.read_text(encoding="utf-8-sig").splitlines()
                     if (x := line.split("#", 1)[0].strip()))


def systems(providers: Sequence[str], options: Any) -> list:
    """An adapter for each provider at its options. `options` maps a provider to its options, or to a list
    of them for several runs of one provider."""
    from omni_parse_bench import harness

    options = options or {}
    if not isinstance(options, dict):
        raise errors.UsageError(f"--options is a JSON object of options per provider, not {options!r}")
    if bad := sorted(set(options) - set(providers)):
        raise errors.UsageError(f"--options names {bad}, which aren't in --providers {list(providers)}")
    out = []
    for p in providers:
        o = options.get(p, {})
        out += [harness.system(p, x) for x in (o if isinstance(o, list) else [o])]
    return out


def cmd_run(a: argparse.Namespace) -> int:
    from omni_parse_bench import benchmark

    outputs = a.outputs or list(vocab.OUTPUT_TYPES)
    b = benchmark.default(a.dataset, a.manifest, outputs)
    xs = systems(a.providers, read_json(a.options, "--options"))
    p = b.plan(xs, a.out, suites=a.suites, limit=a.limit, sample=a.sample,
               only=read_ids(a.pages, "--pages") if a.pages else None, timeout=a.timeout,
               workers=read_json(a.workers, "--workers") or 0, retry_failed=a.retry_failed)
    if a.score_only:
        deprecated("--score-only", "`opb grade <run folder>`")
        if never := [str(r.folder) for r in p.runs if not r.predictions.is_dir()]:
            raise errors.UsageError(f"no run at {never[0]}: this provider with these options was never "
                                    "predicted under this --out")
        print(json.dumps({r.name: b.grade(r) for r in p.runs}, indent=2, default=str))
        return 0
    print(b.describe(p), file=sys.stderr)
    if not a.yes and sys.stdin.isatty():
        sys.stderr.write("  proceed? [y/N] ")
        sys.stderr.flush()
        if input().strip().lower() not in ("y", "yes"): return 1
    try:
        b.predict(p)
    except Exception:
        # Note: what was predicted is graded even when predicting failed part way, so a stopped run still
        # reports what it has; not after an interrupt, because whoever stopped it wants it stopped.
        graded = {r.name: b.grade(r) for r in p.runs if r.predictions.is_dir()}
        print(json.dumps(graded, indent=2, default=str))
        raise
    print(json.dumps({r.name: b.grade(r) for r in p.runs}, indent=2, default=str))
    return 0


def cmd_grade(a: argparse.Namespace) -> int:
    from omni_parse_bench import benchmark

    said = runs.Run.at(a.run).settings()
    dataset = a.dataset or said.get("dataset") or data.DEFAULT_DATASET
    if a.dataset is None and said.get("commit"): dataset = f"{dataset}@{said['commit']}"
    unsupported = a.unsupported if a.unsupported is not None else said.get("unsupported")
    if unsupported is not None:
        old = "--unsupported" if a.unsupported is not None else f"`unsupported` in {a.run}/settings.json"
        deprecated(old, "--outputs, naming the outputs to grade")
    b = benchmark.default(dataset, a.manifest or said.get("manifest") or data.MANIFEST,
                          supported(a.outputs, unsupported) or list(vocab.OUTPUT_TYPES))
    print(json.dumps(b.grade(a.run), indent=2, default=str))
    return 0


def cmd_reparse(a: argparse.Namespace) -> int:
    """`opb reparse`, deprecated: reads each run's saved answers again with the current adapter code, with no
    call."""
    from omni_parse_bench import benchmark, harness

    deprecated("`opb reparse`", "`Benchmark.reread(run)`; grade the run afterwards")
    if a.add:
        raise errors.UsageError("--add is no longer possible: a run's answers hold only the outputs it asked "
                                "for; predict the run again with --outputs")
    for folder in a.runs:
        said = runs.Run.at(folder).settings()
        if not said.get("provider"):
            raise errors.UsageError(f"{folder} is not a run made by predicting, so it has no answers to read "
                                    "again")
        # Note: a model id is the provider, so the LLM adapter's `model` can't also be given as an option.
        options = {k: v for k, v in said.get("settings", {}).items()
                   if not ("/" in said["provider"] and k == "model")}
        run = runs.Run(Path(folder), harness.system(said["provider"], options))
        b = benchmark.default(said.get("dataset", data.DEFAULT_DATASET), said.get("manifest", data.MANIFEST))
        print(json.dumps({run.name: {"changed": len(b.reread(run))}}), file=sys.stdout)
    return 0


def cmd_score(a: argparse.Namespace) -> int:
    """One verdict per test of the page that reads one of `--outputs`."""
    pred = read_object(a.pred, "--pred")
    if pred and not set(pred) & set(vocab.OUTPUT_TYPES):
        hint = (" It looks like a gold file; --pred is the outputs, {output type: value}." if "tests" in pred
                else "")
        raise errors.UsageError(f"--pred {a.pred} holds none of the output types {list(vocab.OUTPUT_TYPES)}, "
                                f"only {sorted(pred)[:5]}.{hint}")
    if a.unsupported is not None:
        deprecated("--unsupported", "--outputs, naming the outputs to grade")
    outputs = set(supported(a.outputs, a.unsupported) or vocab.OUTPUT_TYPES)
    tests = [t for t in unit_tests.tests.read(a.gold) if t.output_type in outputs]
    print(json.dumps([v._asdict() for v in unit_tests.score(pred, tests)], indent=2, ensure_ascii=False))
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    """One page through one system: its record as JSON, without the raw answers unless `--raw`. Exits 1 when
    the page failed."""
    from omni_bench_core import adapter

    from omni_parse_bench import harness

    page = Path(a.page)
    if not page.is_file(): raise errors.UsageError(f"--page {page}: no such file")
    system = harness.system(a.provider, read_json(a.options, "--options"))
    wants = frozenset(a.wants or system.SUPPORTS)
    if missing := sorted(wants - system.SUPPORTS):
        raise errors.UsageError(f"{a.provider} can't produce {missing}; it produces "
                                f"{sorted(system.SUPPORTS)}")
    record = adapter.predict(system, harness.Input(page, wants), timeout=a.timeout)
    if not a.raw: record.pop("raw")
    print(json.dumps(record, indent=2, ensure_ascii=False, default=str))
    return 1 if record["error"] else 0


def cmd_check(a: argparse.Namespace) -> int:
    """Whether a dataset is one opb can run, stopping at the first problem (`Benchmark.check`): its manifest,
    every page file it names, and every gold. It calls no system and runs no test."""
    from omni_parse_bench import benchmark

    b = benchmark.default(a.dataset, a.manifest)
    got = b.check()
    inputs = len({p.doc_path for p in b.rows()})
    print(json.dumps({"ok": True, "manifest": a.manifest, "pages": got["rows"], "suites": got["suites"],
                      "inputs": inputs}))
    return 0


def cmd_tests(a: argparse.Namespace) -> int:
    """Every test of a dataset as a JSON line, with its page's id, suite and document: a flat table to query
    (polars, DuckDB, pandas), made from the gold files and never stored."""
    _, pages = data.read_manifest(a.dataset, a.manifest)
    unit_tests.check(pages)   # Note: first, so only a dataset that checks is written out.
    for p in pages:
        for t in json.loads(Path(p.gt_path).read_text())["tests"]:
            row = {"id": t["id"], "page_id": p.page_id, "suite": p.suite, "document": p.document} | t
            print(json.dumps(row, ensure_ascii=False))
    return 0


def cmd_providers(a: argparse.Namespace) -> int:
    """Every provider and its outputs; or one provider's options, their defaults and what each does. The
    options are the adapter's own fields, so this can't drift from what the adapter takes."""
    from omni_parse_bench import harness

    if not a.provider:
        for name in (*harness.PROVIDERS, *EXAMPLE_MODELS):
            print(f"{name:24} {', '.join(sorted(harness.adapter_class(name).SUPPORTS))}")
        print("\nmodel ids are examples: any OpenRouter org/model id works.")
        return 0
    for f in dataclasses.fields(harness.adapter_class(a.provider)):
        default = "(required)" if f.default is dataclasses.MISSING else repr(f.default)
        print(f"{f.name:24} {default:24} {f.metadata.get('help', '')}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Results go to stdout as JSON; progress and messages go to stderr. `run` shows its plan and asks before
    calling a system, unless given `-y` or run with no terminal. A `UsageError` (what was asked is wrong) or a
    `Stop` (an account, a key or a dependency) is printed as `opb <command>: <what was wrong>` and exits 1; an
    interrupt exits 130; anything else is a bug of ours, and is raised as it is.

    Commands and flags from before 1.0 still work for now, and each prints what replaced it (`deprecated`):

        opb benchmark      is `opb run`, with the same flags
        opb reparse        reads each run's saved answers again (`Benchmark.reread`); `--add` is no longer
                           possible
        --score-only       on `opb run`: grades the runs already on disk and predicts nothing; use `opb grade`
        --unsupported      on `opb grade` and `opb score`: grades every output but these; use `--outputs`. A
                           folder whose settings.json says `unsupported` is graded the same way
    """
    ap = argparse.ArgumentParser(prog="opb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", aliases=["benchmark"],
                       help="predict every page with each provider, then grade; resumable")
    r.add_argument("--providers", nargs="+", required=True, metavar="NAME")
    r.add_argument("--options", metavar="JSON",
                   help='per provider: {"datalab": {"mode": "balanced"}}, or a list of such for several runs')
    r.add_argument("--dataset", default=data.DEFAULT_DATASET, help="a dataset folder, or hf://datasets/<repo>[@rev]")
    r.add_argument("--manifest", default=data.MANIFEST, help="which of the dataset's manifests")
    r.add_argument("--out", type=Path, default=Path("runs"), help="where run folders go")
    r.add_argument("--outputs", nargs="+", choices=vocab.OUTPUT_TYPES,
                   help="the outputs to ask for and grade")
    r.add_argument("--suites", nargs="+", help="only these suites")
    r.add_argument("--limit", type=int, default=0, help="the first N pages")
    r.add_argument("--sample", type=int, default=0, help="N pages spread over every suite")
    r.add_argument("--pages", type=Path, help="a file of page ids, one per line: only these pages")
    r.add_argument("--timeout", type=float, default=900, help="seconds per page")
    r.add_argument("--workers", metavar="N|JSON", help='pages at once per adapter: N, or {"datalab": 20}')
    r.add_argument("--retry-failed", action="store_true",
                   help="predict again pages whose failure may not recur: timeouts, outages, 429 and 5xx")
    r.add_argument("-y", "--yes", action="store_true", help="don't ask before calling systems")
    r.add_argument("--score-only", action="store_true", help=argparse.SUPPRESS)   # Note: deprecated.

    g = sub.add_parser("grade", help="grade a folder of predictions/<page_id>.json: yours, or a run's")
    g.add_argument("run", help="the folder holding predictions/")
    g.add_argument("--dataset", help="default: the one the folder's settings.json names, else ours")
    g.add_argument("--manifest",
                   help="default: the one the folder's settings.json names, else manifest.parquet")
    g.add_argument("--outputs", nargs="+", choices=vocab.OUTPUT_TYPES, help="the outputs to grade")
    g.add_argument("--unsupported", nargs="*", choices=vocab.OUTPUT_TYPES, help=argparse.SUPPRESS)

    s = sub.add_parser("score", help="one page's outputs against its tests: one verdict per test")
    s.add_argument("--pred", required=True, help="the outputs, JSON: {output type: value}")
    s.add_argument("--gold", required=True, help="the page's gold file, gold/<page_id>.json")
    s.add_argument("--outputs", nargs="+", choices=vocab.OUTPUT_TYPES, help="only the tests of these outputs")
    s.add_argument("--unsupported", nargs="*", choices=vocab.OUTPUT_TYPES, help=argparse.SUPPRESS)

    d = sub.add_parser("predict", help="run one page through one provider")
    d.add_argument("--provider", required=True, help="a provider (opb providers), or an OpenRouter model id")
    d.add_argument("--page", required=True, help="the page, .pdf or .png")
    d.add_argument("--wants", nargs="+", choices=vocab.OUTPUT_TYPES,
                   help="output types to produce (default: all it supports)")
    d.add_argument("--timeout", type=float, default=900, help="seconds for the page")
    d.add_argument("--options", metavar="JSON", help="the provider's options, inline JSON or a file")
    d.add_argument("--raw", action="store_true", help="also print the system's raw answers")

    ck = sub.add_parser("check", help="whether a dataset is one opb can run: its manifest, files and gold")
    ck.add_argument("--dataset", default=data.DEFAULT_DATASET, help="a dataset folder, or hf://datasets/<repo>[@rev]")
    ck.add_argument("--manifest", default=data.MANIFEST, help="which of the dataset's manifests")

    tt = sub.add_parser("tests", help="every test as a JSON line, with its page's id, suite and document")
    tt.add_argument("--dataset", default=data.DEFAULT_DATASET, help="a dataset folder, or hf://datasets/<repo>[@rev]")
    tt.add_argument("--manifest", default=data.MANIFEST, help="which of the dataset's manifests")

    rp = sub.add_parser("reparse", help=argparse.SUPPRESS)
    rp.add_argument("runs", nargs="+", type=Path, metavar="RUN_DIR")
    rp.add_argument("--add", nargs="+", metavar="OUTPUT", help=argparse.SUPPRESS)

    pl = sub.add_parser("providers", help="list the providers, or one provider's options")
    pl.add_argument("provider", nargs="?")

    a = ap.parse_args(argv)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().handlers[:] = [handler]
    logging.getLogger().setLevel(logging.WARNING)
    for name in (__package__, "omni_bench_core"): logging.getLogger(name).setLevel(logging.INFO)
    if a.cmd == "benchmark":
        deprecated("`opb benchmark`", "`opb run`, which takes the same flags")
        a.cmd = "run"
    cmd = {"run": cmd_run, "grade": cmd_grade, "score": cmd_score, "predict": cmd_predict, "check": cmd_check,
           "tests": cmd_tests, "providers": cmd_providers, "reparse": cmd_reparse}[a.cmd]
    try:
        return cmd(a)
    except errors.UsageError as exc:
        print(f"opb {a.cmd}: {exc}", file=sys.stderr)
        return 1
    except errors.Stop as exc:
        rerun = "; fix it and rerun to resume" if a.cmd == "run" else ""
        print(f"opb {a.cmd}: {type(exc).__name__}: {exc}{rerun}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"opb {a.cmd}: interrupted" + ("; rerun to resume" if a.cmd == "run" else ""), file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
