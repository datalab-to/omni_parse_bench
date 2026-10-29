"""The `opb` command: a thin wrapper over `benchmark.default()` and the scorer.

    opb init datalab > datalab.yaml                                # a config: one run, every key written out
    opb run --config datalab.yaml --set rows.sample=20             # predict its system, then grade: a new run
    opb resume RUN_DIR [--retry-failed] [--set timeout=...]        # continue a run where it stopped
    opb grade RUN_DIR [--partial]                                  # a folder of predictions/, yours or a run
    opb reread RUN_DIR [RUN_DIR ...]                               # read saved answers again, after a fix
    opb score --pred outputs.json --gold gold/<page_id>.json       # one page's verdicts
    opb predict --system datalab --page pages/<page_id>.pdf        # one page through one system
    opb check --dataset <folder or hf://...>                       # is the dataset one opb can run?
    opb tests --dataset <folder or hf://...> > tests.jsonl         # every test as a JSON line
    opb systems [NAME]                                             # the systems, or one's options

A run is one config (omni-bench-core's `config`): the dataset, its manifest, the scorers, which rows, and
one system with every option. `--set path=value` changes one value the file has. To compare systems, write
one config per system, with the same `rows`. Each run folder keeps its config, resolved, as `config.yaml`.
"""
from __future__ import annotations

import argparse
import dataclasses
import functools
import importlib.metadata
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from omni_bench_core import config
from omni_bench_core import run as runs

from omni_parse_bench import data, errors, vocab
from omni_parse_bench.scorers import unit_tests

EXAMPLE_MODELS = ("openai/gpt-5.6-sol",)
OUTPUTS_IGNORED = ("each page asks for the outputs its tests read, and the summary's families show each part "
                   "(html: text, tables; blocks: layout)")


def deprecated(old: str, new: str) -> None:
    """Says on stderr that `old` is deprecated, and what to use instead."""
    print(f"opb: {old} is deprecated and will be removed in a later release; use {new}", file=sys.stderr)


def ignored(old: str, why: str) -> None:
    """Says on stderr that `old` is deprecated and does nothing, and why."""
    print(f"opb: {old} is deprecated and ignored: {why}", file=sys.stderr)


# Note: each pre-1.0 flag that was renamed, as (its dest, the new flag's dest, the old flag, the new flag).
RENAMED = (
    ("provider", "system", "--provider", "--system"),
    ("wants", "outputs", "--wants", "--outputs"),
)


def renamed(a: argparse.Namespace) -> None:
    """Moves each renamed pre-1.0 flag given onto its new name, saying so (`deprecated`)."""
    for old, new, old_flag, new_flag in RENAMED:
        if getattr(a, old, None) in (None, False): continue
        deprecated(old_flag, new_flag)
        if getattr(a, new, None) not in (None, False):
            raise ValueError(f"{old_flag} is the old name of {new_flag}; give {new_flag} only")
        setattr(a, new, getattr(a, old))


def ignore_outputs(a: argparse.Namespace) -> None:
    """Says that `--outputs` and the old `--unsupported` are ignored, when given (`ignored`)."""
    if getattr(a, "outputs", None): ignored("--outputs", OUTPUTS_IGNORED)
    if getattr(a, "unsupported", None) is not None: ignored("--unsupported", OUTPUTS_IGNORED)


def recorded(said: dict[str, Any], dataset: str | None = None,
             manifest: str | None = None) -> tuple[str, str]:
    """The dataset (at the commit it was run on) and the manifest a run's settings.json names, unless given;
    ours for a folder that names none."""
    d = dataset or said.get("dataset") or data.DEFAULT_DATASET
    if dataset is None and said.get("dataset_commit"): d = f"{d}@{said['dataset_commit']}"
    return d, manifest or said.get("manifest") or data.MANIFEST


def proceed() -> bool:
    """Whether the person at the terminal says yes. Ctrl-D is a no."""
    sys.stderr.write("  proceed? [y/N] ")
    sys.stderr.flush()
    try:
        return input().strip().lower() in ("y", "yes")
    except EOFError:
        sys.stderr.write("\n")
        return False


def read_object(path: str, flag: str) -> dict:
    """The JSON object in the file `path` that `flag` names."""
    try:
        got = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise ValueError(f"{flag} {path}: no such file") from None
    except IsADirectoryError:
        raise ValueError(f"{flag} {path} is a folder; pass a JSON file") from None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ValueError(f"{flag} {path} isn't JSON: {exc}") from None
    if not isinstance(got, dict):
        kind = "null" if got is None else type(got).__name__
        raise ValueError(f"{flag} {path} holds a JSON {kind}; it must be a JSON object")
    return got


def read_json(value: str | None, flag: str) -> Any:
    """A flag's JSON: inline, or a path to a JSON file."""
    if not value: return None
    is_file = Path(value).is_file()
    try:
        return json.loads(Path(value).read_text(encoding="utf-8-sig") if is_file else value)
    except json.JSONDecodeError as e:
        raise ValueError(f"{flag} {value!r} is neither JSON nor a JSON file: {e}") from None


def bare(name: str, options: Any) -> Any:
    """`--options` of `opb predict` for the one system `name`: the bare object, or `{name: {...}}`. An
    object keyed by other systems is refused: a command runs one system."""
    from omni_parse_bench import harness

    if not isinstance(options, dict) or not options or not all(isinstance(v, dict) for v in options.values()):
        return options
    if list(options) == [name]: return options[name]
    if others := [k for k in options if k != name and (k in harness.ADAPTERS or "/" in k)]:
        raise ValueError(f"--options is keyed by {', '.join(others)}, but this command runs {name}: "
                         f"give {name}'s options alone, as {{\"<option>\": <value>}} or "
                         f"{{\"{name}\": {{...}}}}")
    return options


def cmd_init(a: argparse.Namespace) -> int:
    """A config for one system on the published dataset, graded by its unit tests, as YAML on stdout:
    every page, and every option of the system at its default, so the file says the whole run."""
    import yaml

    from omni_parse_bench import harness

    c = config.template(harness.system, a.system, dataset=data.DEFAULT_DATASET, manifest=data.MANIFEST,
                        scorers={unit_tests.UnitTests.name: {}}, timeout=900)
    sys.stdout.write(yaml.safe_dump(c, sort_keys=False, width=1000, allow_unicode=True))
    return 0


def cmd_run(a: argparse.Namespace) -> int:
    """Plans the run a config asks, shows the plan and asks, predicts, then grades: always a new run. A run
    that stops part way is continued with `opb resume <its folder>`."""
    return launched(a, config.load(a.config, a.set), a.out)


def cmd_resume(a: argparse.Namespace) -> int:
    """Continues the run in a folder where it stopped, asking the question it answers: its own config.yaml,
    with `--set` for what a resume may change (`timeout`, `workers`). Only pages with no record are asked, or,
    with `--retry-failed`, also those whose failure may not recur."""
    folder = Path(a.folder)
    if not (folder / config.FILE).is_file():
        raise ValueError(f"{folder} has no {config.FILE}; give a run folder that `opb run` made")
    return launched(a, config.load(folder / config.FILE, a.set), folder.parent, folder.name)


def launched(a: argparse.Namespace, c: config.Config, out: Path, resume: str | None = None) -> int:
    """Plans the run `c` asks under `out` (resuming `resume`), shows the plan and asks, predicts, then grades
    it and prints the grading."""
    from omni_parse_bench import harness, task

    b = config.benchmark(c, task.Parse(), {unit_tests.UnitTests.name: unit_tests.UnitTests})
    system = config.system(c, harness.system)
    p = config.plan(c, b, system, out, resume=resume, retry_failed=getattr(a, "retry_failed", False))
    print(b.describe(p), file=sys.stderr)
    if not a.yes and sys.stdin.isatty() and not proceed():
        print(f"opb {a.cmd}: not run", file=sys.stderr)
        return 1
    config.write(c, b, system, p.run.folder)
    b.predict(p)
    print(json.dumps(b.grade(p.run), indent=2, default=str, ensure_ascii=False))
    return 0


def cmd_grade(a: argparse.Namespace) -> int:
    """Grades a run, or a folder of your own predictions, on every test of its pages. A run is graded on the
    dataset and manifest its settings.json names; a folder of your own, on ours unless given."""
    from omni_parse_bench import benchmark

    ignore_outputs(a)
    run = runs.Run.at(a.run)
    b = benchmark.default(*recorded(run.settings(), a.dataset, a.manifest))
    print(json.dumps(b.grade(run, partial=a.partial), indent=2, default=str, ensure_ascii=False))
    return 0


def cmd_reread(a: argparse.Namespace) -> int:
    """Reads each run's saved answers again with the current adapter code (`Benchmark.reread`), with no call:
    the system is rebuilt from the run's settings.json. Prints how many records changed, then says to grade
    each run again."""
    from omni_parse_bench import benchmark, harness

    if a.cmd == "reparse":
        deprecated("`opb reparse`", "`opb reread`")
        if a.add:
            raise ValueError("--add is no longer possible: each page asks for the outputs its tests "
                             "read; run `opb reread` with no --add")
    for folder in a.runs:
        said = runs.Run.at(folder).settings()
        if not said.get("system"):
            raise ValueError(f"{folder} has no system in its settings.json, so it is a folder of "
                             "your own predictions with no answers to read again; grade it with "
                             "`opb grade`")
        # Note: a model id is the system's name, so the LLM adapter's `model` can't also be an option.
        options = {k: v for k, v in said.get("options", {}).items()
                   if not ("/" in said["system"] and k == "model")}
        system = harness.system(said["system"], options)
        changed = benchmark.default(*recorded(said)).reread(folder, system)
        print(json.dumps({folder.name: {"changed": len(changed)}}))
        print(f"opb {a.cmd}: {folder}: {errors.counted(len(changed), 'record')} changed; grade it again: "
              f"opb grade {folder}", file=sys.stderr)
    return 0


def cmd_score(a: argparse.Namespace) -> int:
    """One verdict per test of the page."""
    pred = read_object(a.pred, "--pred")
    if pred and not set(pred) & set(vocab.OUTPUT_TYPES):
        hint = (" It looks like a gold file; --pred is the outputs, {output type: value}." if "tests" in pred
                else "")
        raise ValueError(f"--pred {a.pred} holds none of the output types {list(vocab.OUTPUT_TYPES)}, "
                         f"only {sorted(pred)[:5]}.{hint}")
    ignore_outputs(a)
    tests = unit_tests.tests.read(a.gold)
    print(json.dumps([v._asdict() for v in unit_tests.score(pred, tests)], indent=2, ensure_ascii=False))
    return 0


def cmd_predict(a: argparse.Namespace) -> int:
    """One page through one system: its record as JSON, without the raw answers unless `--raw`; exits 1
    when the page failed. With no manifest row, it asks for every output the system supports, or for
    `--outputs`."""
    from omni_bench_core import adapter
    from omni_bench_core import errors as core_errors

    from omni_parse_bench import harness

    page = Path(a.page)
    if not page.is_file(): raise ValueError(f"--page {page}: no such file")
    system = harness.system(a.system, bare(a.system, read_json(a.options, "--options")))
    wants = frozenset(a.outputs or system.SUPPORTS)
    if missing := sorted(wants - system.SUPPORTS):
        raise ValueError(f"{a.system} can't produce {', '.join(missing)}; it produces "
                         f"{', '.join(sorted(system.SUPPORTS))}: give --outputs "
                         f"{' '.join(sorted(system.SUPPORTS))}, or leave --outputs out")
    try:
        record = adapter.predict(system, harness.Input(page, wants), timeout=a.timeout)
    except Exception as exc:
        what = "reading the answer of" if hasattr(exc, "unread") else "predicting"
        core_errors.noted(exc, type(system), f"{what} {page}")
        raise
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
    print(json.dumps({"ok": True, "manifest": a.manifest, "pages": got["rows"],
                      "suites": len({p.suite for p in b.rows()}), "inputs": inputs}))
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


def cmd_systems(a: argparse.Namespace) -> int:
    """Every system, its outputs and the environment variables it needs; or one system's options, their
    defaults and what each does, then what its environment needs. The options are the adapter's own fields,
    so this can't drift from what the adapter takes."""
    from omni_parse_bench import harness
    from omni_parse_bench.harness import adapter

    if not a.system:
        for name in (*harness.PROVIDERS, *EXAMPLE_MODELS):
            c = harness.adapter_class(name)
            print(f"{name:24} {', '.join(sorted(c.SUPPORTS)):14} {', '.join(c.keys) or '-'}")
        print("\nmodel ids are examples: any OpenRouter org/model id works. `opb systems NAME` gives a "
              "system's options.")
        return 0
    c = harness.adapter_class(a.system)
    for f in dataclasses.fields(c):
        if f.default is not dataclasses.MISSING: default = repr(f.default)
        elif f.default_factory is not dataclasses.MISSING: default = repr(f.default_factory())
        else: default = "(required)"
        print(f"{f.name:24} {default:24} {adapter.option_help(f)}")
    print("\nenvironment: " + (" and ".join(f"export {k}=..." for k in c.keys) or "no key needed"))
    if c.ENV: print(f"             {c.ENV}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Results go to stdout as JSON; progress and messages to stderr. `run` shows its plan and asks before
    calling a system, unless given `-y` or run with no terminal; any answer but yes exits 1. An interrupt
    exits 130. Anything else is raised as it is, a native exception whose message says what to do.

    Some commands and flags from before 1.0 still work, and each prints what replaced it, or that it is
    ignored; `opb run`'s old flags are gone:

        opb providers      is `opb systems`
        opb reparse        is `opb reread`; `--add` is no longer possible
        --provider         on `opb predict`: is `--system`
        --wants            on `opb predict`: is `--outputs`
        --outputs          on `opb grade` and `opb score`: ignored, since each page asks for the
                           outputs its tests read
        --unsupported      on `opb grade` and `opb score`: ignored"""
    parser = functools.partial(argparse.ArgumentParser, allow_abbrev=False)
    ap = parser(prog="opb", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--version", action="version",
                    version=f"opb {importlib.metadata.version('omni-parse-bench')}")
    sub = ap.add_subparsers(dest="cmd", required=True, metavar="COMMAND", parser_class=parser)
    dataset_help = "a dataset folder, or hf://datasets/<repo>[@rev] (default: %(default)s)"
    manifest_help = "which of the dataset's manifests (default: %(default)s)"

    n = sub.add_parser("init", help="a config for one system, as YAML on stdout")
    n.add_argument("system", help="a system (`opb systems`), or an OpenRouter model id")

    r = sub.add_parser("run", help="predict every page with one config's system, then grade; a new run")
    r.add_argument("--config", required=True, metavar="YAML",
                   help="the run: a config, as `opb init` writes one")
    r.add_argument("--set", action="append", default=[], metavar="PATH=VALUE",
                   help="change one value the config has, read as YAML, e.g. rows.sample=20; repeatable")
    r.add_argument("--out", type=Path, default=Path("runs"),
                   help="where run folders go (default: %(default)s)")
    r.add_argument("-y", "--yes", action="store_true", help="don't ask before calling systems")

    u = sub.add_parser("resume", help="continue a run where it stopped, then grade")
    u.add_argument("folder", help="the run's folder, as opb run made it")
    u.add_argument("--set", action="append", default=[], metavar="PATH=VALUE",
                   help="change what a resume may change, timeout or workers, e.g. timeout=1800; repeatable")
    u.add_argument("--retry-failed", action="store_true",
                   help="predict again pages whose failure may not recur: timeouts, outages, 429 and 5xx")
    u.add_argument("-y", "--yes", action="store_true", help="don't ask before calling systems")

    g = sub.add_parser("grade", help="grade a folder of predictions/<page_id>.json: yours, or a run's")
    g.add_argument("run", help="the folder holding predictions/")
    g.add_argument("--dataset", help="default: the one the folder's settings.json names, else ours")
    g.add_argument("--manifest",
                   help="default: the one the folder's settings.json names, else manifest.parquet")
    g.add_argument("--partial", action="store_true",
                   help="grade an unfinished run anyway: its pages with no answer (or no score) fail, "
                        "and the summary counts them under `partial`; scores.jsonl names each")
    g.add_argument("--outputs", nargs="+", help=argparse.SUPPRESS)
    g.add_argument("--unsupported", nargs="*", help=argparse.SUPPRESS)

    rr = sub.add_parser("reread", help="read each run's saved answers again with the current adapter code, "
                                       "with no call; then grade it again")
    rr.add_argument("runs", nargs="+", type=Path, metavar="RUN_DIR")
    rp = sub.add_parser("reparse")   # Note: no help, so it is left out of `opb --help`; it is deprecated.
    rp.add_argument("runs", nargs="+", type=Path, metavar="RUN_DIR")
    rp.add_argument("--add", nargs="+", metavar="OUTPUT", help=argparse.SUPPRESS)

    s = sub.add_parser("score", help="one page's outputs against its tests: one verdict per test")
    s.add_argument("--pred", required=True, help="the outputs, JSON: {output type: value}")
    s.add_argument("--gold", required=True, help="the page's gold file, gold/<page_id>.json")
    s.add_argument("--outputs", nargs="+", help=argparse.SUPPRESS)
    s.add_argument("--unsupported", nargs="*", help=argparse.SUPPRESS)

    d = sub.add_parser("predict", help="run one page through one system")
    who = d.add_mutually_exclusive_group(required=True)
    who.add_argument("--system", help="a system (`opb systems`), or an OpenRouter model id")
    who.add_argument("--provider", help=argparse.SUPPRESS)
    d.add_argument("--page", required=True, help="the page, .pdf or .png")
    d.add_argument("--outputs", nargs="+", choices=vocab.OUTPUT_TYPES,
                   help="the outputs to ask for, such as html alone to try a page with fewer calls (default: "
                        "every one the system supports)")
    d.add_argument("--wants", nargs="+", choices=vocab.OUTPUT_TYPES, help=argparse.SUPPRESS)
    d.add_argument("--timeout", type=float, default=900, help="seconds for the page (default: %(default)g)")
    d.add_argument("--options", metavar="JSON",
                   help='the system\'s options, inline JSON or a file: {"mode": "fast"}')
    d.add_argument("--raw", action="store_true", help="also print the system's raw answers")

    ck = sub.add_parser("check", help="whether a dataset is one opb can run: its manifest, files and gold")
    ck.add_argument("--dataset", default=data.DEFAULT_DATASET, help=dataset_help)
    ck.add_argument("--manifest", default=data.MANIFEST, help=manifest_help)

    tt = sub.add_parser("tests", help="every test as a JSON line, with its page's id, suite and document")
    tt.add_argument("--dataset", default=data.DEFAULT_DATASET, help=dataset_help)
    tt.add_argument("--manifest", default=data.MANIFEST, help=manifest_help)

    pl = sub.add_parser("systems", aliases=["providers"], help="list the systems, or one system's options")
    pl.add_argument("system", nargs="?", help="a system's name, to list its options and environment")

    argv = list(sys.argv[1:] if argv is None else argv)
    a = ap.parse_args(argv)
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.getLogger().handlers[:] = [handler]
    logging.getLogger().setLevel(logging.WARNING)
    for name in (__package__, "omni_bench_core"): logging.getLogger(name).setLevel(logging.INFO)
    if a.cmd == "providers":
        deprecated("`opb providers`", "`opb systems`")
        a.cmd = "systems"
    cmd = {"init": cmd_init, "run": cmd_run, "resume": cmd_resume, "grade": cmd_grade,
           "score": cmd_score, "predict": cmd_predict, "check": cmd_check,
           "tests": cmd_tests, "systems": cmd_systems, "reread": cmd_reread, "reparse": cmd_reread}[a.cmd]
    try:
        renamed(a)
        return cmd(a)
    except KeyboardInterrupt:
        hint = "; continue it with opb resume <its folder>" if a.cmd in ("run", "resume") else ""
        print(f"opb {a.cmd}: interrupted{hint}", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
