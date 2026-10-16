"""The whole benchmark: read the dataset, predict with each provider, score, write it down.

    opb benchmark --providers datalab openai/gpt-5.6-sol --out runs/
    opb benchmark --providers datalab --limit 5              # smoke test

Two levels of data, each a NamedTuple, and functions over them:

    Plan   the invocation      every Run, and the pages (`data.Page`) they cover; `plan(...)` builds it
    Run    one configuration   a provider plus its options, and the directory it writes to

`execute(plan)` is `predict_all`, then `grade_all`. `describe(plan)` says what it would do, with
no vendor call. Each page is asked for exactly the outputs its tests read.

A run directory holds:

    settings.json                what the run asks: provider, settings, dataset (and commit), timeout,
                                 and the outputs its provider can't produce (`unsupported`)
    predictions/<page_id>.json   the outputs alone, {"html": ..., "blocks": ...}: all grading reads
    records/<page_id>.json       what `predict` returned: outputs, errors, calls, raw responses and
                                 cost, for an audit and for `opb reparse`; grading only sums the cost
    scores.jsonl                 one line per test: its verdict, what the test is (page, suite,
                                 document, type, tags, ...), and the stamps of what graded it
    summary.json                 scorer.summarize over every graded page, plus cost and coverage

Resumable: a page is predicted again only for the outputs its record lacks. Grading is fresh every
time: every predicted page is graded again, and scores.jsonl and summary.json are written whole, so a
run's scores are always one grading's, by this opb against this dataset's gold. A folder of predictions/
made by anything (your own model) is graded the same way, with what it can't produce said in its
settings.json (`opb grade`). A run never mixes datasets. Concurrency is per adapter, not per run:
every run of one adapter (two datalab modes, every OpenRouter model) shares one pool of `_workers_for`
its adapter. Credentials come from the environment
and everything else from `--options`.

    pip install 'omni-parse-bench[benchmark]'
"""
from __future__ import annotations

import collections
import concurrent.futures as cf
import hashlib
import importlib.metadata
import json
import logging
import os
import threading
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from omni_parse_bench import data, vocab
from omni_parse_bench.scorers import unit_tests as scorer

# Note: calls in flight at one vendor, shared by every run of its adapter. A vendor's rate limit is
# per account, so two datalab modes or ten OpenRouter models must not each get a full pool.
WORKERS = {"datalab": 10, "reducto": 3, "extend": 5, "llamaparse": 3, "azure": 3, "mistral": 5, "llm": 5,
           "tesseract": min(8, os.cpu_count() or 1)}
DEFAULT_WORKERS = 5
log = logging.getLogger(__name__)


# The code a verdict depends on: a change to any of it is a new scorer.
PACKAGE = Path(__file__).parent   # the package's folder, which SCORING's paths are relative to
SCORING = ("scorers/unit_tests/__init__.py", "scorers/unit_tests/tests.py", "scorers/unit_tests/runners.py",
           "vocab.py", "views.py", "normalize.py", "tables.py", "equations.py", "katex/katex.js")


def scorer_version() -> str:
    """The package's version and a digest of its scoring code, stamped on each score line: which scorer
    graded it.

    Note: the version alone is the same across every commit between releases, so it can't say the
    scoring changed; the digest of the files that decide a verdict can. The version is kept for the
    reader: which release graded a line.
    """
    try:
        version = importlib.metadata.version("omni-parse-bench")
    except importlib.metadata.PackageNotFoundError:
        version = "unknown"
    h = hashlib.sha256()
    for name in SCORING: h.update((PACKAGE / name).read_bytes())
    return f"{version}+{h.hexdigest()[:12]}"


SCORER = scorer_version()


class Run(NamedTuple):
    """One configuration and its folder: an address, as a `Path` is. What a run holds is whatever its
    folder holds when it is read, so a run is resumed, graded or shared between processes as it stands.
    The functions below are the bookkeeping of any loop over its pages, so a loop of your own (another
    machine, another scheduler) keeps a run exactly as `predict_all` does:

        prepare(run, dataset, timeout, manifest)      # once: the folder, and settings.json
        need = needs(run, page)                       # the outputs the page's record still lacks
        record(run, page_id, harness.predict(...))    # the page's new result, merged and written
        grade(run, pages)                             # scores.jsonl and summary.json, as they stand

    A run folder assumes its pages don't change under it: a dataset is pinned to a commit and its pages
    are never edited in place. Predicting again after a dataset's pages change is a new folder."""

    provider: str
    options: dict
    out: Path

    @property
    def records(self) -> Path:
        return self.out / "records"

    @property
    def predictions(self) -> Path:
        return self.out / "predictions"


def prepare(run: Run, dataset: str, timeout: float, manifest: str = data.MANIFEST) -> None:
    """The run's folder made, and what the run asks written to its settings.json, beside what it already
    says: provider, settings, dataset (and the commit of a Hugging Face one), manifest, the timeout per call
    and the outputs its provider can't produce (`unsupported`). What graded it is stamped on its score
    lines and in summary.json."""
    from omni_parse_bench import harness
    from omni_parse_bench.harness import registry

    root, _ = data.read_manifest(dataset, manifest)
    run.records.mkdir(parents=True, exist_ok=True)
    run.predictions.mkdir(exist_ok=True)
    commit = {"commit": root.name} if str(dataset).startswith(data.HF_PREFIX) else {}
    path = run.out / "settings.json"
    _write_json(path, (_read_json(path) or {}) | {
        "run": run.out.name, "provider": run.provider,
        "settings": harness.settings_for(run.provider, run.options), "dataset": data.dataset_id(dataset),
        **commit, "manifest": manifest, "timeout_s": timeout,
        "unsupported": sorted(set(vocab.OUTPUT_TYPES) - registry.adapter(run.provider).SUPPORTS)})


def recorded(run: Run, page_id: str) -> dict | None:
    """The page's record, the audit trail of its calls (`records/`), or None when it has none (or none
    readable)."""
    got = _read(run.records / f"{page_id}.json",
                lambda r: isinstance(r, dict) and isinstance(r.get("outputs"), dict) and "calls" in r,
                "a record")
    return got


def predicted(run: Run, page_id: str) -> dict | None:
    """The page's outputs (`predictions/`), `{output type: its value, or None when it failed}`; None
    when it has none (or none readable)."""
    return _read(run.predictions / f"{page_id}.json",
                 lambda o: isinstance(o, dict) and set(o) <= set(vocab.OUTPUT_TYPES),
                 f"a prediction (an object whose keys are among {list(vocab.OUTPUT_TYPES)})")


def needs(run: Run, page: data.Page, retry_failed: bool = False) -> frozenset[str]:
    """The outputs the run still lacks for the page: of those the manifest says to predict for it
    (`page.outputs`), what its record doesn't settle (`_missing`).

    Note: a page whose prediction can't be read counts as having no record, so it is predicted again:
    grading reads predictions alone, and a record without one would leave the page pending for good.
    `opb reparse` rebuilds the predictions from the records without a call."""
    old = recorded(run, page.page_id) if predicted(run, page.page_id) is not None else None
    return _missing(old, frozenset(page.outputs), retry_failed)


def record(run: Run, page_id: str, result: dict) -> dict:
    """What `harness.predict` returned for the page made part of the run, and returned: merged into its old
    record if any (`_merged`: the outputs asked again take the new outcome, every call is kept), its outputs
    written to predictions/, then the record itself."""
    old = recorded(run, page_id)
    kept = _merged(old, result) if old is not None else result
    _write_json(run.predictions / f"{page_id}.json", kept["outputs"])
    _write_json(run.records / f"{page_id}.json", kept)
    return kept


class Plan(NamedTuple):
    runs: tuple[Run, ...]
    pages: tuple[data.Page, ...]
    dataset: str
    manifest: str                      # which of the dataset's manifests: its pages, where their gold is
    timeout: float
    workers: int | Mapping[str, int]   # calls in flight: one number for every adapter, or per adapter
    score_only: bool
    retry_failed: bool = False


def _tests(page: data.Page) -> tuple[scorer.Test, ...]:
    """The page's tests (`scorer.gold`), read once per process.

    Note: cached because reading them is the slow part of grading (each LaTeX arg is rendered by
    KaTeX: about 2 s for the whole dataset), and one invocation reads them once per run. The cache
    keys on the page's gold file, not its contents, so a gold file edited in a process that has
    already read it isn't read again: restart the process, or `_TESTS.clear()`."""
    if page.gt_path not in _TESTS:
        _TESTS[page.gt_path] = scorer.gold(page)
    return _TESTS[page.gt_path]


_TESTS: dict[str, tuple[scorer.Test, ...]] = {}   # `_tests`, by gold file


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


def plan(providers: list[str], *, out: str | Path = Path("runs"), dataset: str = data.DEFAULT_DATASET,
         manifest: str = data.MANIFEST, suites: list[str] | None = None, limit: int = 0, sample: int = 0,
         options: dict | None = None,
         timeout: float = 0, workers: int = 0,
         score_only: bool = False, retry_failed: bool = False, only: frozenset[str] | None = None) -> Plan:
    """Every run this invocation makes, checked before any call: a bad option or provider fails here.

    `workers` is the calls in flight per adapter, shared by its runs: one number for every adapter, or
    a number per adapter (`_per_adapter`); 0, or an adapter left out, takes `WORKERS`."""
    from omni_parse_bench import harness

    counts = [("--limit", limit), ("--sample", sample)]
    if isinstance(workers, int): counts.append(("--workers", workers))
    for name, n in counts:
        if n < 0: raise ValueError(f"{name} is {n}, but it counts, so it can't be negative; 0 means no limit")
    if isinstance(workers, Mapping): workers = _per_adapter(workers)
    runs = tuple(Run(p, o, Path(out) / harness.out_name(p, o)) for p, o in configurations(providers, options))
    if twice := [r for r, n in collections.Counter(r.out.name for r in runs).items() if n > 1]:
        raise ValueError(f"run {twice[0]} is asked for more than once: the same provider with the same "
                         "settings (an option set to its default is the same setting); drop the repeat from "
                         "--providers or --options")
    root, every = data.read_manifest(dataset, manifest)
    ps = data.select(every, suites, limit, sample, only)
    commit = root.name if str(dataset).startswith(data.HF_PREFIX) else None
    ident = data.dataset_id(dataset)
    for r in runs:
        said = _read_json(r.out / "settings.json") or {}
        if (was := said.get("dataset", ident)) != ident:
            raise ValueError(f"{r.out} is a run on dataset {was}, not {ident}, and a run never mixes "
                             f"datasets; pass another --out, or --dataset {was}")
        if (msg := _another_commit(r, said.get("commit"), commit)) is not None:
            log.warning("%s", msg)
    return Plan(runs, ps, str(dataset), manifest, timeout or harness.DEFAULT_TIMEOUT, workers, score_only,
                retry_failed)


def _another_commit(r: Run, was: str | None, now: str | None) -> str | None:
    """A warning when a run made at one commit of its dataset is planned at another, else None.

    Note: warned, not refused: a new commit is usually a gold correction, which grading takes in on its
    own. But the run's pages were predicted at the old commit, so a changed page would be graded on an
    old prediction; a new --out keeps the two apart."""
    if was is None or now is None or was == now: return None
    return (f"{r.out} was predicted at commit {was} of its dataset, and this is commit {now}: its "
            "predictions will be graded against this commit's gold. If the pages changed, pass another "
            "--out to predict them again")


def _workers_for(adapter: str, requested: int | Mapping[str, int] = 0) -> int:
    """Calls in flight at once for every run of this adapter (`registry.resolve`) together: what was
    requested (one number for every adapter, or a number per adapter), else `WORKERS`."""
    if isinstance(requested, Mapping): requested = requested.get(adapter, 0)
    return requested or WORKERS.get(adapter, DEFAULT_WORKERS)


def _per_adapter(workers: Mapping[str, int]) -> dict[str, int]:
    """`--workers` as a number per adapter, checked. The limit is a vendor account's, shared by every
    run of its adapter (every OpenRouter model id shares llm's), so it is set per adapter, never per
    provider or model."""
    from omni_parse_bench.harness import registry

    adapters = {m.__name__.rsplit(".", 1)[-1] for m in registry.ADAPTERS.values()} | {"llm"}
    for key, n in workers.items():
        if key not in adapters:
            try:
                a = registry.resolve(key)
                hint = f"{key} uses the {a} adapter, whose pool all its runs share; write {{\"{a}\": {n}}}"
            except ValueError:
                hint = f"the adapters are {sorted(adapters)}"
            raise ValueError(f"--workers is per adapter, and {key!r} isn't one: {hint}")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise ValueError(f"--workers gives {key!r} {n!r}; calls at once is a whole number, 1 or more")
    return dict(workers)


def owed(p: Plan, r: Run) -> tuple[int, int]:
    """How many of the plan's pages this run will predict, and grade, by the rules `predict_all` and
    `grade_all` follow."""
    predict = grade = 0
    for g in p.pages:
        coming = not p.score_only and bool(needs(r, g, p.retry_failed))
        predict += coming
        grade += coming or predicted(r, g.page_id) is not None
    return predict, grade


def describe(p: Plan) -> str:
    """What `execute(p)` would do, as plain text (`progress.plan_view`), with no vendor call."""
    from omni_parse_bench import progress

    return progress.describe(p)


def _write_json(path: Path, obj: Any) -> None:
    """Written whole, then moved into place, so a crash never leaves half a file."""
    _write_text(path, json.dumps(obj, ensure_ascii=False) + "\n")


def _write_text(path: Path, text: str) -> None:
    """`_write_json` for any text."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _read_json(path: Path) -> Any:
    """A JSON file's value, or None when there is no file or it doesn't parse (logged)."""
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("%s isn't readable JSON (%s); it is treated as absent", path, exc)
        return None


def _read(path: Path, valid: Callable[[Any], bool], what: str) -> Any:
    """A run file's contents; None when it's absent, or unreadable or not `what` (logged), which makes its
    page one not predicted."""
    try:
        got = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("%s isn't readable JSON (%s); its page counts as not predicted", path, exc)
        return None
    if not valid(got):
        log.warning("%s isn't %s; its page counts as not predicted", path, what)
        return None
    return got


def unsupported(run: Run) -> frozenset[str]:
    """The outputs the run's system can't produce, whose tests are `unsupported` rather than failed, as
    its settings.json says (`prepare` writes it from the adapter; `opb grade --unsupported` from you).

    Note: one set for the whole run, never read off a page: a prediction that leaves out an output its
    page asks for fails that output's tests, so leaving out hard pages can't take them out of a score."""
    path = run.out / "settings.json"
    said = (_read_json(path) or {}).get("unsupported")
    if said is None:
        raise ValueError(f"{path} doesn't say which outputs the run can't produce. Add \"unsupported\": [] "
                         "(or e.g. [\"blocks\"]) to it, or pass --unsupported to opb grade")
    if not (isinstance(said, list) and set(said) <= set(vocab.OUTPUT_TYPES)):
        raise ValueError(f"{path}: unsupported must be a list of output types from "
                         f"{list(vocab.OUTPUT_TYPES)}, not {said!r}")
    return frozenset(said)


def predict_all(p: Plan) -> None:
    """Predict what each run's records lack. Every run of one adapter drains through that adapter's
    one pool (`_workers_for`), the adapters go at once, and a live table shows each run (`progress.py`)."""
    from omni_parse_bench import harness, progress

    # Note: set on an interrupt, so no run starts another page; a call already made is let finish.
    stop = threading.Event()
    by: dict[str, list[Run]] = {}
    for r in p.runs:
        prepare(r, p.dataset, p.timeout, p.manifest)
        by.setdefault(harness.resolve(r.provider), []).append(r)

    def one(r: Run, g: data.Page, bar: progress.Reporter, halt: threading.Event) -> None:
        if stop.is_set() or halt.is_set(): return
        if not (asked := needs(r, g, p.retry_failed)):
            bar.kept()
            return
        if not (file := Path(g.doc_path)).exists():
            # Note: a page whose file is missing isn't the vendor's failure: nothing is recorded, so
            # it is neither graded nor held against it, and a resume tries again.
            log.warning("%s: no page file for %s at %s", r.out.name, g.page_id, file)
            bar.record(error=True, usd=0, wall_s=0)
            return
        with bar.calling():
            new = harness.predict(r.provider, file, asked, timeout=p.timeout, **r.options)
        record(r, g.page_id, new)
        failed = any(why != "unsupported" for why in new["errors"].values())
        bar.record(error=failed, usd=sum(c["usd"] or 0 for c in new["calls"]),
                   wall_s=sum(c["wall_s"] for c in new["calls"]))

    def drain(adapter: str, runs: list[Run], bars: progress.Progress) -> None:
        """Every page of every run of one adapter, through its one pool."""
        workers = _workers_for(adapter, p.workers)
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


def _missing(record: dict | None, want: frozenset[str], retry_failed: bool = False) -> frozenset[str]:
    """The outputs in `want` (what a page's tests read) that a record doesn't settle: all of them without
    a record, otherwise those it was never asked for. One recorded unsupported is settled. With
    `retry_failed`, also those whose failure may not recur (`_retryable`)."""
    if record is None: return want
    unsupported = {o for o, why in record.get("errors", {}).items() if why == "unsupported"}
    out = want - set(record["outputs"]) - unsupported
    if retry_failed:
        out |= {o for o in want - unsupported if record["outputs"].get(o) is None and _retryable(record, o)}
    return frozenset(out)


def _retryable(record: dict, output: str) -> bool:
    """Whether an output's failure may go the other way on another try: a timeout, an outage, a
    transient HTTP status, or none. A 400, a vendor's failed job or an LLM reply cut at its length,
    refused or never usable (each an answer, status 200) is final; one that arrived but didn't parse is
    `opb reparse`'s, which costs nothing."""
    from omni_parse_bench.harness import errors

    calls = [c for c in record.get("calls", []) if output in c.get("outputs", ())]
    if not calls: return False
    if not isinstance(failure := calls[-1].get("failure"), dict): return False   # it got an answer
    status = failure.get("status")
    return (failure.get("class") in ("VendorTimeout", "VendorUnreachable") or status is None
            or status in errors.TRANSIENT_STATUSES)


def _merged(old: dict, new: dict) -> dict:
    """A record with a later prediction's outputs added: its calls and raw answers follow the old,
    and an output predicted again takes the new outcome, its old error with it. Each call keeps the
    timeout it ran under."""
    errors = {o: why for o, why in old["errors"].items() if o not in new["outputs"]} | new["errors"]
    calls = [c if "timeout_s" in c else c | {"timeout_s": old.get("timeout_s")} for c in old["calls"]]
    latest = {k: new[k] for k in ("timeout_s", "captured_at") if k in new}
    return old | latest | {"outputs": old["outputs"] | new["outputs"], "errors": errors,
                           "calls": calls + new["calls"], "raw": old.get("raw", []) + new.get("raw", [])}


def _grade_page(r: Run, pred: dict, page: data.Page, ts: Sequence[scorer.Test],
                cannot: frozenset[str]) -> list[dict]:
    """One page's score lines (`scorer.lines`), one per test, beside the run that made them and the
    scoring code that graded them, so a run's scores are a table to query as they stand. `cannot` is
    what the run's system can't produce (`unsupported`)."""
    head = {"run": r.out.name, "provider": r.provider}
    return [head | x | {"scorer": SCORER} for x in scorer.lines(scorer.score(pred, ts, cannot), ts, page)]


def _errors_in(summary: dict) -> int:
    """Tests whose grading failed in our code, over every output type; 0 when the summary has no count."""
    return sum((summary.get(o) or {}).get("errors", 0) or 0 for o in vocab.OUTPUT_TYPES
               if isinstance(summary.get(o), dict))


def _headline(name: str, summary: dict) -> str:
    """One run's scores, with the coverage they stand on."""
    scores = ", ".join(f"{o} {100 * s['score']:.1f}" for o in vocab.OUTPUT_TYPES
                       if isinstance(s := summary.get(o), dict) and s.get("score") is not None)
    errs = _errors_in(summary)
    return (f"{name}: {scores or 'no score'} over {summary['pages']} pages graded, "
            f"{summary['pending']} pending" + (f"; {errs} tests errored in our code" if errs else ""))


def grade(run: Run, pages: Sequence[data.Page], say: Callable[[str], None] = print) -> dict:
    """Grade every page of `pages` the run has a prediction for, and write its scores and summary; returns
    the summary. `pages` is usually the whole dataset (`data.read_manifest(dataset)`), as `grade_all`
    passes it.

    Grading reads predictions/ alone, the run's `unsupported` and each page's gold file (`gt_path`);
    records add only their cost to the summary, so a folder of predictions made by anything is graded the
    same way. Given the whole dataset, it covers every page, whatever `--suites` and `--limit` chose to
    predict.

    A page with no prediction is pending (left out, and counted) only when the run's records say it was
    never attempted: no record either, in a folder that keeps records (`prepare` makes `records/`).
    Otherwise it fails, every test of it: a call that failed, or a folder of your own predictions
    (no `records/`), where a page left out is a page your system didn't answer.

    Every page is graded fresh, every time, and scores.jsonl and summary.json are written whole once it
    finishes: they are always one grading's, of `pages`, never a mix. An interrupted grading writes
    nothing, so the last finished one's files stand. Each line says which scorer graded it. A run that
    was never prepared is refused: its folder is most likely another one (another option, another
    --out)."""
    if not run.predictions.is_dir():
        raise ValueError(f"no run at {run.out}: {run.provider} with settings {run.options or 'by default'} "
                         "was never prepared there (it has no predictions/). Check --out and --options, or "
                         "prepare it first")
    cannot = unsupported(run)
    keeps_records = run.records.is_dir()
    lines, calls, pending = [], [], 0
    for g in pages:
        pred, rec = predicted(run, g.page_id), recorded(run, g.page_id)
        if pred is None and rec is None and keeps_records:
            pending += 1
            continue
        if rec is not None: calls += rec["calls"]
        lines += _grade_page(run, pred or {}, g, _tests(g), cannot)
    _write_text(run.out / "scores.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    summary = scorer.summarize(lines)
    summary |= {"scorer": SCORER, "pages": len(pages) - pending, "pending": pending,
                "usd": round(sum(c.get("usd") or 0 for c in calls), 4),
                "credits": round(sum(c.get("credits") or 0 for c in calls), 4)}
    _write_json(run.out / "summary.json", summary)
    say(_headline(run.out.name, summary))
    return summary


def read_scores(run: Run) -> list[dict]:
    """A run's score lines on disk (scores.jsonl), in file order; [] when it has none. A line that isn't
    readable JSON is left out, and logged."""
    path = run.out / "scores.jsonl"
    if not path.exists(): return []
    out = []
    for n, x in enumerate(path.read_text().splitlines()):
        if not x.strip(): continue
        try:
            out.append(json.loads(x))
        except json.JSONDecodeError:
            log.warning("%s: line %d isn't readable JSON; left out", path, n + 1)
    return out


def grade_all(p: Plan, say: Callable[[str], None] = print) -> dict[str, dict]:
    """`grade` each run of the plan; their summaries by run name."""
    _, every = data.read_manifest(p.dataset, p.manifest)
    return {r.out.name: grade(r, every, say) for r in p.runs}


def execute(p: Plan, say: Callable[[str], None] = print) -> dict[str, dict]:
    """Predict, then grade. What was predicted is graded even when predicting stopped early."""
    try:
        if not p.score_only: predict_all(p)
    finally:
        summaries = grade_all(p, say)
    return summaries
