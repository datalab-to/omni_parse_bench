"""The whole benchmark: read the dataset, predict with each provider, score, write it down.

    opb benchmark --providers datalab openai/gpt-5.6-sol --out runs/
    opb benchmark --providers datalab --limit 5              # smoke test

Two levels of data, each a NamedTuple, and functions over them:

    Plan   the invocation      every Run, and the pages (`gold.Page`) they cover; `plan(...)` builds it
    Run    one configuration   a provider plus its options, and the directory it writes to

`execute(plan)` is `predict_all`, then `grade_all`. `describe(plan)` says what it would do, with
no vendor call. Each page is asked for exactly the outputs its tests read.

A run directory holds:

    settings.json                what the run is: provider, settings, dataset, gold and timeout
    records/<page_id>.json       what `predict` returned: outputs, errors, calls, raw responses, and
                                 a digest of the page file
    predictions/<page_id>.json   the outputs alone, which scoring reads
    scores.jsonl                 one line per test: its verdict, what the test is (page, suite,
                                 document, type, tags, ...), and the stamps of what graded it
    summary.json                 metric.summarize over every graded page, plus cost and coverage

Resumable: a page is predicted again only for the outputs its record lacks (or all of them when its
page file has changed), and graded again only when its lines are missing or out of date: its
record, gold or scorer version differs. A run never mixes datasets. Concurrency is per adapter, not per run:
every run of one adapter (two datalab modes, every OpenRouter model) shares one pool of `workers_for`
its adapter. Credentials come from the environment and everything else from `--options`.

    pip install 'omni-parse-bench[benchmark]'
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import functools
import hashlib
import importlib.metadata
import json
import logging
import os
import threading
import time
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from omni_parse_bench import gold, metric, vocab

# Note: calls in flight at one vendor, shared by every run of its adapter. A vendor's rate limit is
# per account, so two datalab modes or ten OpenRouter models must not each get a full pool.
WORKERS = {"datalab": 10, "reducto": 3, "extend": 5, "llamaparse": 3, "azure": 3, "mistral": 5, "llm": 5,
           "tesseract": min(8, os.cpu_count() or 1)}
DEFAULT_WORKERS = 5
log = logging.getLogger(__name__)
HF_PREFIX = "hf://datasets/"
DEFAULT_DATASET = "hf://datasets/datalab-to/omni_parse_bench"
DOWNLOAD_ATTEMPTS = 5


# The code a verdict depends on: a change to any of it is a new scorer.
SCORING = ("gold.py", "vocab.py", "runners.py", "views.py", "normalize.py", "tables.py", "equations.py",
           "metric.py", "katex/katex.js")


def scorer_version() -> str:
    """The package's version and a digest of its scoring code, stamped on each score line so a new
    scorer regrades.

    Note: the version alone is the same across every commit between releases, so it can't say the
    scoring changed; the digest of the files that decide a verdict can.
    """
    try:
        version = importlib.metadata.version("omni-parse-bench")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    h = hashlib.sha256()
    for name in SCORING: h.update((Path(metric.__file__).parent / name).read_bytes())
    return f"{version}+{h.hexdigest()[:12]}"


SCORER = scorer_version()


class Run(NamedTuple):
    provider: str
    options: dict
    out: Path

    @property
    def records(self) -> Path:
        return self.out / "records"

    @property
    def predictions(self) -> Path:
        return self.out / "predictions"


class Plan(NamedTuple):
    runs: tuple[Run, ...]
    pages: tuple[gold.Page, ...]
    dataset: str
    timeout: float
    workers: int          # calls in flight per adapter; 0: `WORKERS`
    rescore: bool
    score_only: bool
    retry_failed: bool = False


def dataset_root(dataset: str | Path) -> Path:
    """A dataset as a local folder: a path as given, or a Hugging Face dataset downloaded.

    Note: an `hf://datasets/<repo>` dataset fetches only its manifest and gold files here; each
    page file is fetched when it's first read (`page_file`), so a `--limit` run downloads only its
    pages.
    """
    if not str(dataset).startswith(HF_PREFIX):
        root = Path(dataset).expanduser()
        if not (root / gold.MANIFEST).exists():
            raise FileNotFoundError(f"no {gold.MANIFEST} in {root}; pass --dataset a dataset folder "
                                    f"or {HF_PREFIX}<repo>")
        return root
    from huggingface_hub import errors as hf_errors
    from huggingface_hub import snapshot_download

    repo, _, revision = str(dataset).removeprefix(HF_PREFIX).partition("@")
    # Note: thousands of small files; the Hub drops some requests under that load, and a download
    # picks up where the last left off, so it is simply tried again. A missing repo, revision or
    # access is the same on every attempt, so it fails at once.
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            return Path(snapshot_download(repo, repo_type="dataset", revision=revision or None,
                                          allow_patterns=[gold.MANIFEST, "gold/*"], max_workers=4))
        except (hf_errors.RepositoryNotFoundError, hf_errors.GatedRepoError,
                hf_errors.RevisionNotFoundError) as exc:
            raise ValueError(f"can't read dataset {dataset}: {type(exc).__name__}. Check the repo and "
                             "revision, and that you're logged in with access (huggingface-cli login)"
                             ) from None
        except hf_errors.HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise ValueError(f"can't read dataset {dataset}: HTTP {status}. Log in with access to it "
                                 "(huggingface-cli login)") from None
            if attempt == DOWNLOAD_ATTEMPTS - 1: raise
        except Exception:
            if attempt == DOWNLOAD_ATTEMPTS - 1: raise
        time.sleep(30 * (attempt + 1))
    raise AssertionError("unreachable")


def dataset_id(dataset: str | Path) -> str:
    """What a run's dataset is, whatever revision: the repo of an `hf://` dataset, or a folder's path."""
    if str(dataset).startswith(HF_PREFIX): return str(dataset).partition("@")[0]
    return str(Path(dataset).expanduser().resolve())


def gold_revision(dataset: str, root: Path) -> str:
    """Which gold a run is graded against: the Hugging Face commit, or a digest of a folder's gold."""
    if str(dataset).startswith(HF_PREFIX): return root.name   # snapshot_download's folder is the commit
    # Note: the manifest is in it too: its documents decide the document counts.
    h = hashlib.sha256((root / gold.MANIFEST).read_bytes())
    for f in sorted((root / "gold").glob("*.json")):
        h.update(f.name.encode())
        h.update(f.read_bytes())
    return h.hexdigest()[:16]


@functools.cache
def load(dataset: str) -> tuple[Path, tuple[gold.Page, ...], dict[str, tuple[gold.Test, ...]]]:
    """The dataset's folder, its pages, and each page's tests by page id; read once per process."""
    root = dataset_root(dataset)
    ps, ts = gold.load(root)
    return root, ps, gold.by_page(ts)


def page_file(dataset: str, root: Path, doc_path: str) -> Path:
    """A page's file, fetched from Hugging Face the first time for an `hf://` dataset.

    Note: fetched at the commit the gold was read at (`root.name`), not at the branch's head, so a
    commit pushed mid-run can't pair one commit's page with another's gold."""
    path = root / doc_path
    if path.exists() or not str(dataset).startswith(HF_PREFIX): return path
    from huggingface_hub import hf_hub_download

    repo = str(dataset).removeprefix(HF_PREFIX).partition("@")[0]
    return Path(hf_hub_download(repo, doc_path, repo_type="dataset", revision=root.name))


def local_page(dataset: str, root: Path, doc_path: str) -> Path | None:
    """A page's file if it is on this machine already, with no network call; else None."""
    path = root / doc_path
    if path.exists() or not str(dataset).startswith(HF_PREFIX): return path if path.exists() else None
    from huggingface_hub import try_to_load_from_cache

    repo = str(dataset).removeprefix(HF_PREFIX).partition("@")[0]
    got = try_to_load_from_cache(repo, doc_path, revision=root.name, repo_type="dataset")
    return Path(got) if isinstance(got, str) else None


def file_digest(path: Path) -> str:
    """A page file's sha256, kept in its record, so a changed page is predicted again."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pages(dataset: str, suites: list[str] | None = None, limit: int = 0,
          sample: int = 0, only: frozenset[str] | None = None) -> tuple[Path, tuple[gold.Page, ...]]:
    """The dataset's folder and its pages, in manifest order, filtered by suite and by `only` (page
    ids, each of which must be in the dataset), and limited.

    `sample` picks that many pages spread over every suite: suites in turn, each page evenly spaced
    within its suite, so a smoke test sees every kind of page and the same pages each time."""
    root, rows, _ = load(str(dataset))
    known = {r.suite for r in rows}
    if bad := sorted(set(suites or ()) - known):
        raise ValueError(f"unknown suites {bad}; the dataset's suites are {sorted(known)}")
    rows = tuple(r for r in rows if not suites or r.suite in suites)
    if only is not None:
        if bad := sorted(only - {r.page_id for r in rows}):
            raise ValueError(f"{len(bad)} of the pages asked for aren't in the dataset"
                             f"{' (or its suites)' if suites else ''}, e.g. {bad[:3]}; nothing has been run")
        rows = tuple(r for r in rows if r.page_id in only)
    if sample:
        by: dict[str, list] = {}
        for r in rows: by.setdefault(r.suite, []).append(r)
        k = -(-sample // len(by))
        spread = [[xs[i * len(xs) // min(k, len(xs))] for i in range(min(k, len(xs)))] for xs in by.values()]
        turns = [x for i in range(k) for xs in spread if i < len(xs) for x in [xs[i]]]
        chosen = {r.page_id for r in turns[:sample]}
        rows = tuple(r for r in rows if r.page_id in chosen)
    return root, rows[:limit] if limit else rows


def configurations(providers: list[str], options: dict | None = None) -> list[tuple[str, dict]]:
    """Each (provider, options) pair to run: a provider's options may be one dict or a list of them."""
    options = options or {}
    if bad := sorted(set(options) - set(providers)):
        raise ValueError(f"--options names {bad}, which aren't in --providers")
    out = []
    for p in providers:
        o = options.get(p, {})
        if o == []:
            raise ValueError(f"--options gives {p} an empty list, which is no run; give it a list of option "
                             "dicts, {} for its defaults, or drop it from --providers")
        out += [(p, x) for x in (o if isinstance(o, list) else [o])]
    return out


def plan(providers: list[str], *, out: str | Path = Path("runs"), dataset: str = DEFAULT_DATASET,
         suites: list[str] | None = None, limit: int = 0, sample: int = 0, options: dict | None = None,
         timeout: float = 0, workers: int = 0, rescore: bool = False,
         score_only: bool = False, retry_failed: bool = False, only: frozenset[str] | None = None) -> Plan:
    """Every run this invocation makes, checked before any call: a bad option or provider fails here.

    `workers` is the calls in flight per adapter, shared by its runs; 0 takes `WORKERS`."""
    from omni_parse_bench import harness

    for name, n in (("--limit", limit), ("--sample", sample), ("--workers", workers)):
        if n < 0: raise ValueError(f"{name} is {n}, but it counts, so it can't be negative; 0 means no limit")
    runs = tuple(Run(p, o, Path(out) / harness.out_name(p, o)) for p, o in configurations(providers, options))
    if twice := [r for r, n in collections.Counter(r.out.name for r in runs).items() if n > 1]:
        raise ValueError(f"run {twice[0]} is asked for more than once: the same provider with the same "
                         "settings (an option set to its default is the same setting); drop the repeat from "
                         "--providers or --options")
    _, ps = pages(dataset, suites, limit, sample, only)
    ident = dataset_id(dataset)
    for r in runs:
        if (was := (read_json(r.out / "settings.json") or {}).get("dataset", ident)) != ident:
            raise ValueError(f"{r.out} is a run on dataset {was}, not {ident}, and a run never mixes "
                             f"datasets; pass another --out, or --dataset {was}")
    return Plan(runs, ps, str(dataset), timeout or harness.DEFAULT_TIMEOUT, workers, rescore, score_only,
                retry_failed)


def workers_for(adapter: str, requested: int = 0) -> int:
    """Calls in flight at once for every run of this adapter (`registry.resolve`) together."""
    return requested or WORKERS.get(adapter, DEFAULT_WORKERS)


PLAN_WIDTH = 110


def facts(p: Plan):
    """What this invocation is, one labelled row each."""
    from rich.table import Table
    from rich.text import Text

    from omni_parse_bench import harness

    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column("", style="dim", no_wrap=True)
    table.add_column("", overflow="fold")
    table.add_row("out", str(p.runs[0].out.parent) if p.runs else "")
    table.add_row("runs", str(len(p.runs)))
    table.add_row("dataset", p.dataset)
    table.add_row("pages", str(len(p.pages)))
    table.add_row("timeout", f"{p.timeout:.0f}s per call")
    adapters = sorted({harness.resolve(r.provider) for r in p.runs})
    table.add_row("at once", ", ".join(f"{a} {workers_for(a, p.workers)}" for a in adapters)
                  + " calls, shared by an adapter's runs")
    # Note: shown even when false: `score only  false` is what says this will spend money.
    for name, on in (("score only", p.score_only), ("rescoring", p.rescore)):
        table.add_row(name, Text(str(on).lower(), style="bold" if on else "dim"))
    return table


def owed(p: Plan, r: Run, revision: str, page_digest: Callable[[gold.Page], str | None]) -> tuple[int, int]:
    """How many of the plan's pages this run will predict, and grade, by the rules `predict_all` and
    `grade_all` follow. `page_digest` is a page file's digest when it is at hand with no download."""
    _, _, tests = load(p.dataset)
    rows = {} if p.rescore else read_scores(r.out / "scores.jsonl")
    predict = grade = 0
    for g in p.pages:
        got = read_record(r.records / f"{g.page_id}.json")
        record, text = got if got is not None else (None, "")
        sha = page_digest(g) if record is not None and "page_sha256" in record else None
        coming = not p.score_only and bool(missing(record, gold.wants(tests[g.page_id]), p.retry_failed, sha))
        predict += coming
        grade += coming or (record is not None and not current(rows.get(g.page_id), text, revision,
                                                                 tests[g.page_id]))
    return predict, grade


def plan_view(p: Plan):
    """The whole plan as one renderable: each run, its settings, and what it still owes."""
    from rich import box
    from rich.console import Group
    from rich.rule import Rule
    from rich.table import Table
    from rich.text import Text

    from omni_parse_bench import harness

    root, _, _ = load(p.dataset)
    revision = gold_revision(p.dataset, root)

    @functools.cache
    def page_digest(g: gold.Page) -> str | None:
        return None if (f := local_page(p.dataset, root, g.doc_path)) is None else file_digest(f)

    table = Table(box=box.ROUNDED, header_style="dim", expand=False)
    table.add_column("adapter", overflow="fold")
    table.add_column("run", overflow="fold")
    table.add_column("settings", overflow="fold")
    table.add_column("predict", justify="right", no_wrap=True)
    table.add_column("grade", justify="right", no_wrap=True)
    for r in p.runs:
        to_predict, to_grade = owed(p, r, revision, page_digest)
        settings = [f"{k}={v}" for k, v in harness.settings_for(r.provider, r.options).items()]
        cell: list = []
        for n, x in enumerate(settings):
            if n: cell.append(Rule(style="dim"))
            cell.append(Text(x, style="cyan"))
        table.add_row(Text(harness.resolve(r.provider), style="bold"), Text(r.out.name), Group(*cell),
                      Text(str(to_predict), style="bold" if to_predict else ""),
                      Text(str(to_grade), style="bold" if to_grade else ""), end_section=True)
    return Group(Text("benchmark", style="bold"), facts(p), Text(""), table)


def describe(p: Plan) -> str:
    """`plan_view` as plain text, for a log that has no colour and no width to ask about."""
    import io

    from rich.console import Console

    console = Console(file=io.StringIO(), width=PLAN_WIDTH, no_color=True, highlight=False)
    console.print(plan_view(p))
    return "\n".join(line.rstrip() for line in console.file.getvalue().splitlines())


def write_json(path: Path, obj: Any) -> None:
    """Written whole, then moved into place, so a crash never leaves half a file."""
    write_text(path, json.dumps(obj, ensure_ascii=False) + "\n")


def write_text(path: Path, text: str) -> None:
    """`write_json` for any text."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    """A JSON file's value, or None when there is no file or it doesn't parse (logged)."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("%s isn't readable JSON (%s); it is treated as absent", path, exc)
        return None


def read_record(path: Path) -> tuple[dict, str] | None:
    """A record and the digest of its text, or None when it's absent or unreadable (logged), which
    makes its page one not predicted."""
    try:
        text = path.read_text()
        record = json.loads(text)
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("%s isn't readable JSON (%s); its page counts as not predicted", path, exc)
        return None
    if not (isinstance(record, dict) and isinstance(record.get("outputs"), dict) and "calls" in record):
        log.warning("%s isn't a record; its page counts as not predicted", path)
        return None
    return record, digest(text)


def read_scores(path: Path) -> dict[str, list[dict]]:
    """A run's scores, each page's lines by its id; a line that doesn't parse, or lacks a test's id,
    result or why, is left out, so its page is graded again."""
    if not path.exists(): return {}
    out, bad = collections.defaultdict(list), 0
    for line in path.read_text().splitlines():
        if not line.strip(): continue
        try:
            row = json.loads(line)
            if not (isinstance(row.get("test_id"), str) and "result" in row and "why" in row):
                raise KeyError("test_id")
            out[row["page_id"]].append(row)
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            bad += 1
    if bad: log.warning("%s: %d line(s) not read; their pages are graded again", path, bad)
    return dict(out)


def settle(r: Run, **facts: Any) -> None:
    """`facts` written into the run's settings.json, beside what it already says."""
    path = r.out / "settings.json"
    was = read_json(path) or {}
    now = was | facts
    if (g := facts.get("gold")) and was.get("gold") not in (None, g):
        # Note: a gold change regrades the run; the golds it has been read against are kept in order.
        now["golds"] = [*was.get("golds", [was["gold"]]), g]
    write_json(path, now)


def predict_all(p: Plan) -> None:
    """Predict what each run's records lack. Every run of one adapter drains through that adapter's
    one pool (`workers_for`), the adapters go at once, and a live table shows each run (`progress.py`)."""
    from omni_parse_bench import harness, progress

    root, _, tests = load(p.dataset)
    revision = gold_revision(p.dataset, root)
    # Note: set on an interrupt, so no run starts another page; a call already made is let finish.
    stop = threading.Event()
    by: dict[str, list[Run]] = {}
    for r in p.runs:
        r.records.mkdir(parents=True, exist_ok=True)
        r.predictions.mkdir(exist_ok=True)
        settle(r, run=r.out.name, provider=r.provider, settings=harness.settings_for(r.provider, r.options),
               dataset=dataset_id(p.dataset), gold=revision, timeout_s=p.timeout)
        by.setdefault(harness.resolve(r.provider), []).append(r)

    def one(r: Run, g: gold.Page, bar: progress.Reporter, halt: threading.Event) -> None:
        if stop.is_set() or halt.is_set(): return
        want, path = gold.wants(tests[g.page_id]), r.records / f"{g.page_id}.json"
        old = None if (got := read_record(path)) is None else got[0]
        # Note: a record from before page digests is trusted, so resuming an old run fetches no page
        # only to check it.
        if old is not None and "page_sha256" not in old and not missing(old, want, p.retry_failed):
            bar.kept()
            return
        try:
            file = page_file(p.dataset, root, g.doc_path)
            sha = file_digest(file)
        except Exception as exc:  # noqa: BLE001
            # Note: a page whose file can't be had isn't the vendor's failure: nothing is
            # recorded, so it is neither graded nor held against it, and a resume tries again.
            log.warning("%s: no page file for %s: %s", r.out.name, g.page_id, str(exc)[:200])
            bar.record(error=True, usd=0, wall_s=0)
            return
        if not (asked := missing(old, want, p.retry_failed, sha)):
            bar.kept()
            return
        with bar.calling():
            new = harness.predict(r.provider, file, asked, timeout=p.timeout, **r.options)
        new["page_sha256"] = sha
        # Note: a record of another page file is replaced, not added to.
        record = merged(old, new) if old is not None and old.get("page_sha256", sha) == sha else new
        write_json(r.predictions / f"{g.page_id}.json", record["outputs"])
        write_json(path, record)
        failed = any(why != "unsupported" for why in new["errors"].values())
        bar.record(error=failed, usd=sum(c["usd"] or 0 for c in new["calls"]),
                   wall_s=sum(c["wall_s"] for c in new["calls"]))

    def drain(adapter: str, runs: list[Run], bars: progress.Progress) -> None:
        """Every page of every run of one adapter, through its one pool."""
        workers = workers_for(adapter, p.workers)
        reporters = {r.out.name: bars.reporter(r.out.name) for r in runs}
        for x in reporters.values(): x.start(len(p.pages), workers)
        halt = threading.Event()
        ex = cf.ThreadPoolExecutor(workers)
        try:
            # Note: the runs' pages are interleaved, so an adapter's runs advance together.
            fs = [ex.submit(one, r, g, reporters[r.out.name], halt) for g in p.pages for r in runs]
            for f in cf.as_completed(fs): f.result()
        except BaseException as exc:
            # Note: an account or credential failure is the same for every page and every run of the
            # adapter (one key), so all of them stop now and the pages still queued are never sent.
            halt.set()
            ex.shutdown(wait=False, cancel_futures=True)
            if isinstance(exc, Exception):
                log.error("%s: stopped its runs (%s): %s: %s", adapter, ", ".join(r.out.name for r in runs),
                          type(exc).__name__, str(exc)[:300])
            raise
        finally:
            ex.shutdown(wait=True)
        for x in reporters.values(): x.finish()

    failures: list[Exception] = []
    with progress.Progress([r.out.name for r in p.runs]) as bars:
        with cf.ThreadPoolExecutor(max(1, len(by))) as ex:
            fs = [ex.submit(drain, a, runs, bars) for a, runs in by.items()]
            try:
                for f in cf.as_completed(fs):
                    # Note: one adapter's failure (its key, its account) is its own, so the others go on;
                    # an interrupt (Ctrl-C) stops them all.
                    try: f.result()
                    except Exception as exc: failures.append(exc)
            except BaseException:
                stop.set()
                raise
    if failures: raise failures[0]


def missing(record: dict | None, want: frozenset[str], retry_failed: bool = False,
            page_sha: str | None = None) -> frozenset[str]:
    """The outputs in `want` (what a page's tests read) that a record doesn't settle: all of them without
    a record or when it is of another page file (`page_sha`, when given and the record has one), and
    otherwise those it was never asked for. One recorded unsupported is settled. With `retry_failed`,
    also those whose failure may not recur (`retryable`)."""
    if record is None: return want
    if page_sha is not None and record.get("page_sha256", page_sha) != page_sha: return want
    unsupported = {o for o, why in record.get("errors", {}).items() if why == "unsupported"}
    out = want - set(record["outputs"]) - unsupported
    if retry_failed:
        out |= {o for o in want - unsupported if record["outputs"].get(o) is None and retryable(record, o)}
    return frozenset(out)


def retryable(record: dict, output: str) -> bool:
    """Whether an output's failure may go the other way on another try: a timeout, an outage, a
    transient HTTP status, or none. A 400, a vendor's failed job or an LLM reply cut at its length,
    refused or never usable (each an answer, status 200) is final; one that arrived but didn't parse is
    `opb reparse`'s, which costs nothing."""
    from omni_parse_bench.harness import errors

    calls = [c for c in record.get("calls", []) if output in c.get("outputs", ())]
    if not calls: return False
    if isinstance(failure := calls[-1].get("failure"), dict):
        status = failure.get("status")
        return (failure.get("class") in ("VendorTimeout", "VendorUnreachable") or status is None
                or status in errors.TRANSIENT_STATUSES)
    # Note: a call without a failure got an answer, or is from before calls recorded their failure;
    # then only its error's class, which starts the error's text, is read, and only a timeout or an
    # outage is tried again.
    why = str(record.get("errors", {}).get(output, ""))
    return why.startswith(("VendorTimeout:", "VendorUnreachable:"))


def merged(old: dict, new: dict) -> dict:
    """A record with a later prediction's outputs added: its calls and raw answers follow the old,
    and an output predicted again takes the new outcome, its old error with it. Each call keeps the
    timeout it ran under."""
    errors = {o: why for o, why in old["errors"].items() if o not in new["outputs"]} | new["errors"]
    calls = [c if "timeout_s" in c else c | {"timeout_s": old.get("timeout_s")} for c in old["calls"]]
    latest = {k: new[k] for k in ("timeout_s", "captured_at", "page_sha256") if k in new}
    return old | latest | {"outputs": old["outputs"] | new["outputs"], "errors": errors,
                           "calls": calls + new["calls"], "raw": old.get("raw", []) + new.get("raw", [])}


def digest(text: str) -> str:
    """A record's digest, kept on its page's score lines, so a changed record is graded again."""
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def current(lines: Sequence[dict] | None, record: str, revision: str, tests: Sequence[gold.Test]) -> bool:
    """Whether a page's score lines still stand: they grade the record whose digest is `record`, against
    this gold and with this scorer, one line for each of the page's tests (a renamed test is graded
    again)."""
    if not lines: return False
    return (all(x.get("record") == record and x.get("gold") == revision and x.get("scorer") == SCORER
                for x in lines)
            and sorted(x["test_id"] for x in lines) == sorted(t.id for t in tests))


def grade_page(r: Run, record: dict, record_digest: str, page: gold.Page, tests: Sequence[gold.Test],
               revision: str) -> list[dict]:
    """One page's score lines, one per test: the verdict beside what its test is, so a run's scores
    are a table to query as they stand, stamped with what they grade and what graded them."""
    unsupported = {o for o, why in record.get("errors", {}).items() if why == "unsupported"}
    vs = metric.score(record["outputs"], tests, unsupported)
    return [{"run": r.out.name, "provider": r.provider, "page_id": page.page_id, "suite": page.suite,
             "document": page.document, "test_id": t.id, "test_type": t.test_type,
             "output_type": t.output_type, "derivation": t.derivation, "tags": list(t.tags),
             "result": v.result, "why": v.why,
             "record": record_digest, "gold": revision, "scorer": SCORER}
            for t, v in zip(tests, vs, strict=True)]


def errors_in(summary: dict) -> int:
    """Tests whose grading failed in our code, over every output type; 0 when the summary has no count."""
    return sum((summary.get(o) or {}).get("errors", 0) or 0 for o in vocab.OUTPUT_TYPES
               if isinstance(summary.get(o), dict))


def headline(name: str, summary: dict) -> str:
    """One run's scores, with the coverage they stand on."""
    scores = ", ".join(f"{o} {100 * s['score']:.1f}" for o in vocab.OUTPUT_TYPES
                       if isinstance(s := summary.get(o), dict) and s.get("score") is not None)
    errs = errors_in(summary)
    return (f"{name}: {scores or 'no score'} over {summary['pages']} pages graded, "
            f"{summary['pages_pending']} pending" + (f"; {errs} tests errored in our code" if errs else ""))


def grade_all(p: Plan, say: Callable[[str], None] = print) -> dict[str, dict]:
    """Grade every recorded page of every run and write its scores and summary; returns summaries.

    Grading covers every page of the dataset a run has a record for, whatever `--suites` and
    `--limit` chose to predict, so a smaller invocation never shrinks a run's scores. A page's lines are
    graded again when they aren't `current`: its record, the gold (`gold_revision`) or the scorer has changed.
    Scores are written however grading ends, so an interrupt keeps what was graded."""
    root, every, tests = load(p.dataset)
    revision = gold_revision(p.dataset, root)
    out = {}
    for r in p.runs:
        if not r.records.is_dir():
            say(f"{r.out.name}: nothing recorded, so nothing to grade")
            continue
        settle(r, gold=revision)
        path = r.out / "scores.jsonl"
        old = {} if p.rescore else read_scores(path)
        lines_of, seen, calls = {}, set(), []
        try:
            for g in every:
                if (got := read_record(r.records / f"{g.page_id}.json")) is not None:
                    record, text = got
                    calls += record["calls"]
                    had, ts = old.get(g.page_id), tests[g.page_id]
                    lines_of[g.page_id] = had if current(had, text, revision, ts) else grade_page(
                        r, record, text, g, ts, revision)
                seen.add(g.page_id)
        finally:
            # Note: a page not reached yet keeps its old lines, which their stamps let the next grading check.
            kept = [lines_of.get(g.page_id) if g.page_id in seen else old.get(g.page_id) for g in every]
            lines = [x for xs in kept for x in xs or ()]
            write_text(path, "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
        ordered = [lines_of[g.page_id] for g in every if g.page_id in lines_of]
        by_id = {t.id: t for g in every if g.page_id in lines_of for t in tests[g.page_id]}
        verdicts = [metric.Verdict(x["test_id"], x["result"], x["why"]) for xs in ordered for x in xs]
        summary = metric.summarize(verdicts, [by_id[v.id] for v in verdicts], every)
        summary |= {"gold": revision, "scorer": SCORER, "pages": len(ordered),
                    "pages_pending": len(every) - len(ordered),
                    "usd": round(sum(c.get("usd") or 0 for c in calls), 4),
                    "credits": round(sum(c.get("credits") or 0 for c in calls), 4)}
        write_json(r.out / "summary.json", summary)
        say(headline(r.out.name, summary))
        out[r.out.name] = summary
    return out


def execute(p: Plan, say: Callable[[str], None] = print) -> dict[str, dict]:
    """Predict, then grade. What was predicted is graded even when predicting stopped early."""
    try:
        if not p.score_only: predict_all(p)
    finally:
        summaries = grade_all(p, say)
    return summaries
