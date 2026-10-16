"""The `opb` command: a thin wrapper over `score`, `predict` and `benchmark`.

    opb score --pred outputs.json --gold gold/<page_id>.json
    opb predict --provider datalab --page pages/<page_id>.pdf
    opb benchmark --providers datalab openai/gpt-5.6-sol --dataset hf://datasets/datalab-to/omni_parse_bench
    opb grade RUN_DIR [--unsupported blocks]           # a folder of predictions/, yours or a run's
    opb check --dataset <folder or hf://...>          # is the dataset one opb can run?
    opb tests --dataset <folder or hf://...> > tests.jsonl
    opb providers [NAME]
    opb reparse RUN_DIR ...

Everything goes to stdout as JSON except `benchmark`'s progress, and `benchmark` shows its plan
and waits for a yes unless given `-y`; nothing in the library ever reads stdin. `benchmark` exits 2
when a test's grading failed in our code, so a scorer bug can't pass as a vendor's score. A mistake in
what was asked (a ValueError or a missing file), and a vendor account's or credential's failure, is
printed as `opb <command>: <what was wrong>`, and exits 1; an interrupt exits 130; anything else is a
bug of ours, and is raised as it is.

`score` needs only the core install; every other command needs an extra (EXTRAS), and on an
install without it says which to add instead of failing on the first missing import.
"""
from __future__ import annotations

import argparse
import dataclasses
import json
import re
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omni_parse_bench import benchmark, data, progress, vocab
from omni_parse_bench.scorers import unit_tests as scorer

# command -> the extra it needs; `score` needs none.
EXTRAS = {"predict": "harness", "providers": "harness", "reparse": "harness", "benchmark": "benchmark",
          "grade": "benchmark", "tests": "benchmark", "check": "benchmark"}



def read_json(path: str) -> Any:
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        raise FileNotFoundError(f"no file at {path}") from None
    except json.JSONDecodeError as e:
        raise ValueError(f"{path} isn't JSON: {e}") from None


def read_workers(value: str) -> int | dict:
    """`--workers` as one number for every adapter, or a JSON object of a number per adapter."""
    try:
        return int(value)
    except ValueError:
        pass
    try:
        out = json.loads(value)
    except json.JSONDecodeError:
        raise argparse.ArgumentTypeError(
            f"--workers is a number, or a JSON object like '{{\"datalab\": 20}}', not {value!r}") from None
    if not isinstance(out, dict):
        raise argparse.ArgumentTypeError(f"--workers must be a number or a JSON object, not {value!r}")
    return out


def read_ids(path: Path) -> frozenset[str]:
    """A file of ids, one per line; blank lines and `#` comments are skipped."""
    if not path.is_file():
        raise FileNotFoundError(f"no file at {path}; --pages is a file of page ids, one per line")
    return frozenset(x for line in path.read_text().splitlines() if (x := line.split("#", 1)[0].strip()))


def read_options(value: str | None) -> dict:
    """`--options` as a dict: inline JSON, or a path to a JSON file."""
    if not value: return {}
    is_file = Path(value).is_file()
    try:
        out = json.loads(Path(value).read_text() if is_file else value)
    except json.JSONDecodeError as e:
        if is_file: raise ValueError(f"--options: {value} isn't JSON: {e}") from None
        if value.lstrip()[:1] in ("{", "["): raise ValueError(f"--options isn't JSON: {e}") from None
        raise ValueError(f"--options {value!r} is neither inline JSON nor a file that exists") from None
    if not isinstance(out, dict):
        raise ValueError(f"--options must be a JSON object, got {type(out).__name__}")
    return out


def cmd_score(a: argparse.Namespace) -> int:
    """What `score` returns: one verdict per test of the page."""
    pred = read_json(a.pred)
    if not isinstance(pred, dict):
        raise ValueError(f"{a.pred} holds a JSON {type(pred).__name__}; a prediction is an object, "
                         '{output type: value}, e.g. {"html": "..."}')
    if pred and not set(pred) & set(vocab.OUTPUT_TYPES):
        hint = (" It looks like a record from opb predict; pass its outputs." if "outputs" in pred else "")
        raise ValueError(f"{a.pred} holds none of the output types {list(vocab.OUTPUT_TYPES)}, only "
                         f"{sorted(pred)[:5]}.{hint}")
    if not Path(a.gold).is_file():
        raise FileNotFoundError(f"no gold file at {a.gold}")
    vs = scorer.score(pred, scorer.tests.read(a.gold), unsupported=set(a.unsupported or ()))
    print(json.dumps([v._asdict() for v in vs], indent=2, ensure_ascii=False))
    return 0


def cmd_check(a: argparse.Namespace) -> int:
    """`opb check`: whether a dataset is one opb can run. It checks, stopping at the first problem:

        1. the manifest, as `data.read_manifest` does: the columns page_id, document, suite, doc_path,
           gt_path and outputs are there; page_id, document, doc_path and gt_path are non-empty
           strings; each page_id is a filename; each suite is a string, or null for "other"; each
           doc_path is a relative path inside the dataset to a .pdf or .png; each gt_path is a
           relative path inside the dataset named `<page_id>.json`; each outputs is a non-empty list
           of distinct output types; and page ids are unique, ignoring case;
        2. every doc_path and gt_path exists as a file; and
        3. every gold, as `unit_tests.check` does: it is JSON holding only `tests`, a list; each test
           has exactly the fields a test has, a non-empty id, a known test_type reading its own
           output_type, a known derivation, known tags, and args and settings of the types its
           test_type takes; the outputs a page's tests read are its manifest `outputs`; no test id is
           used twice; and every page has a test.

    It does not open an input (a PDF isn't checked to be a PDF), or run a test against a prediction.
    The problem goes to stderr, naming its row; a dataset that passes is described on stdout, as JSON,
    and exits 0."""
    _, pages = data.read_manifest(a.dataset, a.manifest)
    if not pages:
        raise ValueError(f"the manifest {a.manifest} names no pages")
    if missing := [f"{p.page_id} {c} {f}" for p in pages for c, f in (("doc_path", p.doc_path),
                   ("gt_path", p.gt_path)) if not Path(f).is_file()]:
        raise ValueError(f"{len(missing)} files the manifest names don't exist, e.g. "
                         + "; ".join(missing[:3]))
    scorer.check(pages)
    print(json.dumps({"ok": True, "manifest": a.manifest, "pages": len(pages),
                      "suites": len({p.suite for p in pages}), "inputs": len({p.doc_path for p in pages})}))
    return 0


def cmd_tests(a: argparse.Namespace) -> int:
    """Every test of a dataset as a JSON line, with its page's id, suite and document: a flat table
    to query (polars, DuckDB, pandas), made from the gold files and never stored."""
    _, pages = data.read_manifest(a.dataset, a.manifest)
    scorer.check(pages)   # Note: first, so only a dataset that checks is written out.
    for p in pages:
        for t in json.loads(Path(p.gt_path).read_text())["tests"]:
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

    Console(stderr=True, highlight=False).print(progress.plan_view(plan))
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
    p = benchmark.plan(a.providers, out=a.out, dataset=a.dataset, manifest=a.manifest,
                       suites=a.suites, limit=a.limit,
                       sample=a.sample, options=read_options(a.options), timeout=a.timeout,
                       workers=a.workers, score_only=a.score_only,
                       retry_failed=a.retry_failed,
                       only=read_ids(a.pages) if a.pages else None)
    if not a.yes and not a.score_only and not confirm_plan(p):
        return 1
    summaries = benchmark.execute(p, lambda s: print(s, file=sys.stderr))
    print(json.dumps(summaries, indent=2, ensure_ascii=False))   # each run's summary.json, by run name
    if errored := {k: n for k, s in summaries.items() if (n := benchmark._errors_in(s))}:
        print(f"warning: grading failed in our code (not the vendor's) for {sum(errored.values())} tests: "
              + ", ".join(f"{k} {n}" for k, n in errored.items())
              + ". They are left out of the scores; report it with the run's scores.jsonl.", file=sys.stderr)
        return 2
    return 0


def cmd_grade(a: argparse.Namespace) -> int:
    """Grade a folder of predictions/<page_id>.json, whatever made them, and print its summary, as its
    summary.json holds it. A folder holds one dataset and one manifest: a run's are in its settings.json, and a folder
    of your own gets them there (with `--unsupported`, what its system can't produce) once its first
    grading succeeds, so a later grading needs no flags and another dataset or manifest is refused.
    `--unsupported` is for your own folders: a run's adapter says what it can't produce."""
    import logging

    logging.basicConfig(level=logging.WARNING, format="%(message)s", stream=sys.stderr)
    out = Path(a.run)
    if not out.is_dir():
        raise FileNotFoundError(f"no folder at {out}; pass the folder holding predictions/<page_id>.json")
    path = out / "settings.json"
    said = benchmark._read_json(path) or {}
    run = benchmark.Run(said.get("provider", out.name), {}, out)
    if a.unsupported is not None and run.records.is_dir():
        raise ValueError(f"{out} is a run, whose adapter says what it can't produce; --unsupported is for a "
                         "folder of your own predictions")
    dataset = a.dataset or said.get("dataset") or data.DEFAULT_DATASET
    if a.dataset and (was := said.get("dataset")) and data.dataset_id(a.dataset) != was:
        raise ValueError(f"{out} is graded on dataset {was}, not {data.dataset_id(a.dataset)}, and a folder "
                         f"never mixes datasets; pass --dataset {was}, or grade a copy without its "
                         "settings.json")
    manifest = a.manifest or said.get("manifest") or data.MANIFEST
    if a.manifest and (was := said.get("manifest")) and a.manifest != was:
        raise ValueError(f"{out} is graded on manifest {was}, not {a.manifest}, and a folder never mixes "
                         f"manifests; pass --manifest {was}, or grade a copy without its settings.json")
    if a.suites and (out / "summary.json").exists():
        print(f"warning: {out}: grading only {', '.join(a.suites)} replaces its summary of every suite with "
              "theirs; grade it without --suites to get it back", file=sys.stderr)
    root, pages = data.read_manifest(dataset, manifest)
    cannot = sorted(set(a.unsupported)) if a.unsupported is not None else None
    s = benchmark.grade(run, data.select(pages, a.suites), say=lambda m: print(m, file=sys.stderr),
                        among=pages, cannot=cannot)
    if not run.records.is_dir():
        # Note: only once grading succeeded, so a failed one leaves the folder as it was.
        commit = {"commit": root.name} if data._hf_dataset(dataset) is not None else {}
        kept = cannot if cannot is not None else said["unsupported"]
        benchmark._write_json(path, said | {"dataset": data.dataset_id(dataset), **commit,
                                            "manifest": manifest, "unsupported": kept})
    print(json.dumps(s, indent=2, ensure_ascii=False))   # the folder's summary.json
    return 2 if benchmark._errors_in(s) else 0


def cmd_reparse(a: argparse.Namespace) -> int:
    """Read each record's outputs again from its saved answers, with the current adapter code.

    Nothing is paid: a parsing fix reaches a finished run this way. With `--add`, outputs the run
    never asked for are read from its answers too, where they hold them (`harness.reparse`). The run's
    scores are then out of date, and its next grading grades the changed pages again
    (`opb benchmark ... --score-only`, or `opb grade`).
    """
    from omni_parse_bench import harness

    for run in a.runs:
        if not (run / "records").is_dir():
            raise FileNotFoundError(f"no records/ in {run}; reparse reads a run folder's "
                                    "records/<page_id>.json")
        # Note: every record read and reparsed before any is rewritten, so a bad one stops nothing half-done.
        done = []
        for path in sorted((run / "records").glob("*.json")):
            try:
                record = json.loads(path.read_text())
                new = harness.reparse(record, frozenset(a.add or ()))
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                raise ValueError(f"{path} isn't a record opb can reparse ({type(exc).__name__}: {exc}); "
                                 "nothing in this run was rewritten") from None
            if new["outputs"] != record["outputs"] or new["errors"] != record["errors"]:
                done.append((path, new))
        for path, new in done:
            benchmark._write_json(path, new)
            benchmark._write_json(run / "predictions" / path.name, new["outputs"])
        print(f"{run}: {len(done)} of {len(list((run / 'records').glob('*.json')))} records changed"
              + ("; regrade it to see them: opb benchmark ... --score-only, or opb grade " + str(run)
                 if done else ""), file=sys.stderr)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="opb", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("score", help="grade one page's outputs against its tests: one verdict per test")
    s.add_argument("--pred", required=True, help="the outputs, JSON: {output type: value}")
    s.add_argument("--gold", required=True, help="the page's gold file, gold/<page_id>.json")
    s.add_argument("--unsupported", nargs="*", metavar="OUTPUT", choices=vocab.OUTPUT_TYPES,
                   help="output types the provider can't produce")

    d = sub.add_parser("predict", help="run one page through one provider")
    d.add_argument("--provider", required=True, help="a vendor (opb providers), or an OpenRouter model id")
    d.add_argument("--page", required=True, help="the page, .pdf or .png")
    d.add_argument("--wants", nargs="*", metavar="OUTPUT", choices=vocab.OUTPUT_TYPES,
                   help="output types to produce (default: all it supports)")
    d.add_argument("--timeout", type=float, default=900, help="seconds per vendor call")
    d.add_argument("--options", metavar="JSON", help="the provider's options, inline JSON or a file")
    d.add_argument("--raw", action="store_true", help="also print the vendor's raw responses")

    b = sub.add_parser("benchmark", help="predict and score every page, resumably")
    b.add_argument("--providers", nargs="+", required=True, metavar="NAME")
    b.add_argument("--dataset", default=data.DEFAULT_DATASET,
                   help="a dataset folder, or hf://datasets/<repo>[@revision]")
    b.add_argument("--manifest", default=data.MANIFEST,
                    help="which of the dataset's manifests: its pages, and where their gold is")
    b.add_argument("--out", type=Path, default=Path("runs"), help="where run directories go")
    b.add_argument("--suites", nargs="+", help="limit to these suites")
    b.add_argument("--limit", type=int, default=0, help="first N pages")
    b.add_argument("--sample", type=int, default=0, help="N pages spread over every suite; for a smoke test")
    b.add_argument("--pages", type=Path, help="a file of page ids, one per line: run only these pages")
    b.add_argument("--options", metavar="JSON",
                   help='per provider: {"datalab": {"mode": "balanced"}}, or a list of such dicts '
                        "for several runs")
    b.add_argument("--timeout", type=float, default=900, help="seconds per vendor call")
    b.add_argument("--workers", type=read_workers, default=0, metavar="N|JSON",
                   help="calls at once per adapter, shared by its runs: N for every adapter, or a number "
                        'per adapter, e.g. \'{"datalab": 20, "llm": 3}\' (llm: every OpenRouter model id; '
                        "default: a table per vendor)")
    b.add_argument("--score-only", action="store_true", help="grade what's recorded; predict nothing")
    b.add_argument("--retry-failed", action="store_true",
                   help="predict again outputs whose call may go otherwise: timeouts, outages, 429 and 5xx; "
                        "never a 400 or a vendor's answer")
    b.add_argument("-y", "--yes", action="store_true", help="don't ask before calling vendors")

    g = sub.add_parser("grade", help="grade a folder of predictions/<page_id>.json: yours, or a run's")
    g.add_argument("run", help="the folder holding predictions/ (and settings.json)")
    g.add_argument("--dataset", default=None,
                   help="a dataset folder, or hf://datasets/<repo>[@revision]; default: the one the folder's "
                        "settings.json names, else ours")
    g.add_argument("--manifest", default=None,
                   help="which of the dataset's manifests, a path inside it; default: the one the folder's "
                        "settings.json names, else manifest.parquet")
    g.add_argument("--unsupported", nargs="*", metavar="OUTPUT", choices=vocab.OUTPUT_TYPES,
                   help="output types your system can't produce, once for the folder (kept in its "
                        "settings.json); their tests are unsupported, not failed")
    g.add_argument("--suites", nargs="*", metavar="SUITE",
                   help="grade only these suites; otherwise every page, and a page with no prediction fails")

    ck = sub.add_parser("check", help="whether a dataset is one opb can run: its manifest, files and gold")
    ck.add_argument("--dataset", default=data.DEFAULT_DATASET,
                    help="a dataset folder, or hf://datasets/<repo>[@revision]")
    ck.add_argument("--manifest", default=data.MANIFEST,
                    help="which of the dataset's manifests: its pages, and where their gold is")

    tt = sub.add_parser("tests", help="every test as a JSON line, with its page's suite and document")
    tt.add_argument("--dataset", default=data.DEFAULT_DATASET,
                    help="a dataset folder, or hf://datasets/<repo>[@revision]")
    tt.add_argument("--manifest", default=data.MANIFEST,
                     help="which of the dataset's manifests: its pages, and where their gold is")

    rp = sub.add_parser("reparse", help="read outputs again from saved answers, after a parsing fix")
    rp.add_argument("runs", nargs="+", type=Path, metavar="RUN_DIR")
    rp.add_argument("--add", nargs="+", metavar="OUTPUT",
                    help="also read these outputs from the saved answers")

    pl = sub.add_parser("providers", help="list the providers and their options")
    pl.add_argument("provider", nargs="?")

    a = ap.parse_args(argv)
    cmd = {"score": cmd_score, "predict": cmd_predict, "benchmark": cmd_benchmark, "grade": cmd_grade,
           "check": cmd_check, "tests": cmd_tests, "providers": cmd_providers, "reparse": cmd_reparse}[a.cmd]
    try:
        return cmd(a)
    except (ValueError, FileNotFoundError) as exc:   # Note: ManifestError and GoldError are ValueErrors.
        print(f"opb {a.cmd}: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(f"opb {a.cmd}: interrupted; rerun to resume", file=sys.stderr)
        return 130
    except ImportError as exc:
        # Note: only a third-party module is fixed by installing an extra; a broken import of our own
        # must surface as itself. The harness's own error (`MissingDependency`) names its module only
        # in its message.
        missing = exc.name or (m[1] if (m := re.search(r"No module named '([^']+)'", str(exc))) else None)
        if a.cmd not in EXTRAS or not missing or missing.startswith("omni_parse_bench"): raise
        extra = EXTRAS[a.cmd]
        raise ImportError(f"opb {a.cmd} needs {missing.split('.')[0]}, which comes with the {extra} extra: "
                          f"pip install 'omni-parse-bench[{extra}]'", name=exc.name) from exc
    except Exception as exc:
        # Note: the harness's errors are matched only once it is loaded: importing it here would need its
        # extra, which `opb score` doesn't, and an error of a module never loaded was never raised.
        errs = sys.modules.get("omni_parse_bench.harness.errors")
        if errs is None or not isinstance(exc, errs.AccountFailure | errs.MissingCredential): raise
        print(f"opb {a.cmd}: {exc}" + ("; fix it and rerun to resume: what was predicted is kept"
                                         if a.cmd == "benchmark" else ""), file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
