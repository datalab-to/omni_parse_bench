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
settings.json (`opb grade`). A run never mixes datasets or manifests. Concurrency is per adapter, not
per run: every run of one adapter (two datalab modes, every OpenRouter model) shares one pool of
`_workers_for` its adapter. Credentials come from the environment and everything else from `--options`.

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
from collections.abc import Callable, Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any, NamedTuple

from omni_parse_bench import data, vocab
from omni_parse_bench.errors import Stop, UsageError
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
    """The run's folder made, and what the run asks written to its settings.json (`declare`): provider,
    settings, the timeout per call and the outputs its provider can't produce (`unsupported`)."""
    from omni_parse_bench import harness
    from omni_parse_bench.harness import registry

    run.records.mkdir(parents=True, exist_ok=True)
    run.predictions.mkdir(exist_ok=True)
    declare(run.out, dataset, manifest, {
        "run": run.out.name, "provider": run.provider,
        "settings": harness.settings_for(run.provider, run.options), "timeout_s": timeout,
        "unsupported": sorted(set(vocab.OUTPUT_TYPES) - registry.adapter(run.provider).SUPPORTS)})


def settled(out: Path, dataset: str | None = None, manifest: str | None = None) -> dict:
    """The folder's settings.json ({} when it has none), checked against the dataset and manifest asked for
    (None: whatever it says). A folder holds one dataset and one manifest, so another is refused: graded
    against other gold, its scores would be replaced under the same name."""
    said = _said(out)
    for key, now in (("dataset", dataset and data.dataset_id(dataset)), ("manifest", manifest)):
        if now and (was := said.get(key)) and was != now:
            raise UsageError(f"{out} holds a run on {key} {was}, not {now}: a folder holds one dataset and "
                             f"one manifest; pass --{key} {was}, or another folder")
    return said


def declare(out: Path, dataset: str, manifest: str, fields: Mapping[str, Any] | None = None) -> None:
    """Writes the folder's settings.json, whole: `fields`, then the dataset (and the commit it was read at)
    and the manifest it is graded on. `prepare` writes a run's; `opb grade`, a folder of your own's once its
    first grading succeeds."""
    root, _ = data.read_manifest(dataset, manifest)
    commit = data.commit(dataset, root)
    write_json(out / "settings.json", {**(fields or {}), "dataset": data.dataset_id(dataset),
                                       **({"commit": commit} if commit else {}), "manifest": manifest})


def _said(out: Path) -> dict:
    """The folder's settings.json as it stands; {} when it has none."""
    path = out / "settings.json"
    try:
        said = json.loads(path.read_text())
    except FileNotFoundError:
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise UsageError(f"{path} isn't readable JSON ({exc}); fix it, or remove it to start the folder's "
                         "settings over") from None
    if not isinstance(said, dict):
        raise UsageError(f"{path} holds a JSON {type(said).__name__}; settings.json is an object")
    return said


def recorded(run: Run, page_id: str) -> dict | None:
    """The page's record, the audit trail of its calls (`records/`), or None when it has none (or none
    readable, which is logged)."""
    path = run.records / f"{page_id}.json"
    try:
        got = json.loads(path.read_text())
    except FileNotFoundError:
        return None
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("%s isn't readable JSON (%s); it is treated as missing", path, exc)
        return None
    if not (isinstance(got, dict) and isinstance(got.get("outputs"), dict) and "calls" in got):
        log.warning("%s isn't a record; it is treated as missing", path)
        return None
    return got


def predicted(run: Run, page_id: str) -> dict | None:
    """The page's outputs (`predictions/`), `{output type: its value, or None when it failed}`; None when it
    has none, or none readable as a JSON object. Other keys are kept and ignored, as `scorer.score` ignores
    them. Quiet: `grade` says once how many it couldn't read."""
    try:
        got = json.loads((run.predictions / f"{page_id}.json").read_text())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    return got if isinstance(got, dict) else None


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
    write_json(run.predictions / f"{page_id}.json", kept["outputs"])
    write_json(run.records / f"{page_id}.json", kept)
    return kept


def _listed(run: Run) -> frozenset[str]:
    """The file names in predictions/; a prediction is read only under its exact name, so the score and the
    stray-file warning agree on every disk, case-insensitive ones included."""
    return frozenset(f.name for f in run.predictions.iterdir()) if run.predictions.is_dir() else frozenset()


def _tried(run: Run, page_id: str, listed: frozenset[str]) -> bool:
    """Whether the run attempted the page: it has a record, or a prediction (`listed`, by exact name). In a
    folder that keeps records, a page never tried is pending; `grade` and `owed` both follow this."""
    return f"{page_id}.json" in listed or recorded(run, page_id) is not None


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
        raise UsageError(f"--options names {bad}, which aren't in --providers")
    out = []
    for p in providers:
        o = options.get(p, {})
        if o == []:
            raise UsageError(f"--options gives {p} an empty list, which is no run; give it a list of option "
                             "dicts, {} for its defaults, or drop it from --providers")
        out += [(p, x) for x in (o if isinstance(o, list) else [o])]
    return out


def plan(providers: Sequence[str], *, out: str | Path = Path("runs"),
         dataset: str | Path = data.DEFAULT_DATASET, manifest: str = data.MANIFEST,
         suites: Iterable[str] | None = None, limit: int = 0, sample: int = 0, options: dict | None = None,
         timeout: float = 0, workers: int | Mapping[str, int] = 0,
         score_only: bool = False, retry_failed: bool = False, only: Iterable[str] | None = None) -> Plan:
    """Every run this invocation makes, checked before any call: a bad provider, option, count or folder
    fails here.

    `workers` is the calls in flight per adapter, shared by its runs: one number for every adapter, or
    a number per adapter (`_per_adapter`); 0, or an adapter left out, takes `WORKERS`. `timeout` is the
    seconds per call; 0 takes `harness.DEFAULT_TIMEOUT`."""
    from omni_parse_bench import harness

    if isinstance(providers, str):
        raise TypeError(f"providers is a list of names, not the string {providers!r}; pass [{providers!r}]")
    if isinstance(workers, bool) or not isinstance(workers, int | Mapping):
        raise TypeError(f"workers is a number for every adapter, or a mapping of adapter to number, not "
                        f"{workers!r}")
    if isinstance(workers, int) and workers < 0:
        raise UsageError(f"--workers is {workers}, but it counts calls, so it can't be negative; 0 means "
                         "each adapter's default")
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):
        raise TypeError(f"timeout is seconds, a number, not {timeout!r}")
    if timeout < 0:
        raise UsageError(f"--timeout is {timeout}, but it is the seconds per call: a positive number, or 0 "
                         "for the default")
    runs = tuple(Run(p, o, Path(out) / harness.out_name(p, o)) for p, o in configurations(providers, options))
    # Note: after the runs, whose providers are now resolved, so an adapter a plugin declares is known.
    if isinstance(workers, Mapping): workers = _per_adapter(workers)
    if twice := [r for r, n in collections.Counter(r.out.name for r in runs).items() if n > 1]:
        raise UsageError(f"run {twice[0]} is asked for more than once: the same provider with the same "
                         "settings (an option set to its default is the same setting); drop the repeat from "
                         "--providers or --options")
    root, every = data.read_manifest(dataset, manifest)
    if not (ps := data.select(every, suites, limit, sample, only)):
        given = [f for f, v in (("--suites", suites), ("--limit", limit), ("--sample", sample),
                                ("--pages", only is not None)) if v]
        raise UsageError(f"no pages selected: {' and '.join(given)} chose none of the manifest's "
                         f"{len(every)} pages")
    commit = data.commit(dataset, root)
    for r in runs:
        if score_only and not r.predictions.is_dir():
            raise UsageError(f"no run at {r.out}: {r.provider} with these settings was never predicted under "
                             "this --out; check --out and --options, or drop --score-only")
        said = settled(r.out, str(dataset), manifest)
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


def pools(p: Plan) -> dict[str, int]:
    """Each adapter of the plan's runs (`harness.resolve`) and its calls in flight, shared by its runs."""
    from omni_parse_bench import harness

    return {a: _workers_for(a, p.workers) for a in sorted({harness.resolve(r.provider) for r in p.runs})}


def _workers_for(adapter: str, requested: int | Mapping[str, int] = 0) -> int:
    """Calls in flight at once for every run of this adapter together: what was requested (one number for
    every adapter, or a number per adapter), else `WORKERS`."""
    if isinstance(requested, Mapping): requested = requested.get(adapter, 0)
    return requested or WORKERS.get(adapter, DEFAULT_WORKERS)


def _per_adapter(workers: Mapping[str, int]) -> dict[str, int]:
    """`--workers` as a number per adapter, checked. The limit is a vendor account's, shared by every
    run of its adapter (every OpenRouter model id shares llm's), so it is set per adapter, never per
    provider or model."""
    from omni_parse_bench import harness
    from omni_parse_bench.harness import registry

    # Note: the adapters filed so far, which include every plugin a provider of the plan loaded.
    adapters = registry.adapter_names()
    for key, n in workers.items():
        if key not in adapters:
            try:
                a = harness.resolve(key)
                hint = f"{key} uses the {a} adapter, whose pool all its runs share; write {{\"{a}\": {n}}}"
            except UsageError:
                hint = f"the adapters are {sorted(adapters)}"
            raise UsageError(f"--workers is per adapter, and {key!r} isn't one: {hint}")
        if isinstance(n, bool) or not isinstance(n, int) or n < 1:
            raise UsageError(f"--workers gives {key!r} {n!r}; calls at once is a whole number, 1 or more")
    return dict(workers)


def owed(p: Plan, run: Run) -> tuple[int, int]:
    """How many pages the run will predict, and then grade, by the rules `predict_all` and `grade_all`
    follow: it predicts the plan's pages it still needs, and grades every page of the manifest it will have
    attempted (`_tried`; the rest are pending), or every page in a folder without records/."""
    coming = set() if p.score_only else {g.page_id for g in p.pages if needs(run, g, p.retry_failed)}
    _, every = data.read_manifest(p.dataset, p.manifest)
    if p.score_only and not run.records.is_dir(): return 0, len(every)
    listed = _listed(run)
    return len(coming), sum(g.page_id in coming or _tried(run, g.page_id, listed) for g in every)


def describe(p: Plan) -> str:
    """What `execute(p)` would do, as plain text (`progress.plan_view`), with no vendor call."""
    from omni_parse_bench import progress

    return progress.describe(p)


def write_json(path: Path, obj: Any) -> None:
    """Written whole, then moved into place, so a crash never leaves half a file."""
    _write_text(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def _write_text(path: Path, text: str) -> None:
    """`write_json` for any text."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def unsupported(run: Run) -> frozenset[str]:
    """The outputs the run's system can't produce, whose tests are `unsupported` rather than failed, as
    its settings.json says (`prepare` writes it from the adapter; `opb grade --unsupported` from you)."""
    return _unsupported(_said(run.out), run.out)


def _unsupported(said: Mapping[str, Any], out: Path) -> frozenset[str]:
    """`unsupported` from the folder's settings, `said`.

    Note: one set for the whole run, never read off a page: a prediction that leaves out an output its
    page asks for fails that output's tests, so leaving out hard pages can't take them out of a score."""
    if (got := said.get("unsupported")) is None:
        raise UsageError(f"{out} doesn't say which outputs its system can't produce (its settings.json has "
                         "no \"unsupported\"); pass opb grade --unsupported with them, or with none for none")
    if not (isinstance(got, list) and set(got) <= set(vocab.OUTPUT_TYPES)):
        raise UsageError(f"{out / 'settings.json'}: unsupported must be a list of output types from "
                         f"{list(vocab.OUTPUT_TYPES)}, not {got!r}")
    return frozenset(got)


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
            try:
                new = harness.predict(r.provider, file, asked, timeout=p.timeout, **r.options)
            except Exception as exc:
                if not isinstance(exc, Stop):
                    # Note: `predict` records every failure that is a fact about the page, so this is a bug
                    # in the adapter or in ours; recorded, it would pass as the vendor's.
                    exc.add_note(f"{r.out.name}: raised while predicting {g.page_id} with the "
                                 f"{harness.resolve(r.provider)} adapter, a bug rather than the vendor's "
                                 "answer, so its runs stop; what was recorded is kept, and a run after the "
                                 "fix resumes")
                raise
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
                log.error("%s: stopped its runs (%s): %s: %s%s", adapter, ", ".join(r.out.name for r in runs),
                          type(exc).__name__, str(exc)[:300],
                          "".join(f"; {n}" for n in getattr(exc, "__notes__", ())))
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
    """Whether an output's failure may go the other way on another try: a timeout, an outage
    (`VendorUnreachable`), or a transient HTTP status. A 400, a vendor's failed job, or an answer that
    arrived and couldn't be used (an LLM reply cut at its length, refused, unreadable) is final; one that
    didn't parse is `opb reparse`'s, which costs nothing."""
    from omni_parse_bench.harness import errors

    calls = [c for c in record.get("calls", []) if output in c.get("outputs", ())]
    if not calls: return False
    if not isinstance(failure := calls[-1].get("failure"), dict): return False   # it got an answer
    return (failure.get("class") in ("VendorTimeout", "VendorUnreachable")
            or failure.get("status") in errors.TRANSIENT_STATUSES)


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


def scorer_errors(summary: dict) -> int:
    """Tests whose grading raised in our code (verdict `error`), over every output type: a scorer bug, left
    out of the scores; `opb benchmark` and `opb grade` exit 2 when there are any."""
    return sum((summary.get(o) or {}).get("errors", 0) or 0 for o in vocab.OUTPUT_TYPES
               if isinstance(summary.get(o), dict))


def _closing(s: dict) -> str:
    """A grading's one line: the headline, or why there is none, and how many pages were graded and failed."""
    why = (f" ({s['pending']} pending: a headline needs every page)" if s["pending"]
           else " (a family of tests has none scored)")
    head = f"headline {s['headline']:.3f}" if s["headline"] is not None else "headline —" + why
    return (f"{s['run']}: {head}; {s['pages']} of {s['pages'] + s['pending']} pages graded, "
            f"{s['failed']} failed"
            + (f"; {e} tests errored in our code" if (e := scorer_errors(s)) else ""))


def grade(run: Run, pages: Sequence[data.Page], say: Callable[[str], None] = print, *,
          settings: Mapping[str, Any] | None = None) -> dict:
    """Grade the run's folder against `pages`, the manifest's (`grade_all` passes them), write its
    scores.jsonl and summary.json, and return the summary. `settings` is the folder's settings.json as
    `opb grade` will write it once grading succeeds; otherwise it is read from the folder.

    A page's prediction is `predictions/<page_id>.json`, named exactly. A page never attempted (`_tried`)
    in a folder that keeps records is pending; otherwise a page with no prediction fails, every test of
    it. docs/API.md has the summary's fields."""
    gradable(run.out)
    said = _said(run.out) if settings is None else settings
    lines, count, calls, unread = _graded(run, pages, _unsupported(said, run.out))
    summary = _summary(run, said, lines, count, calls)
    _write_text(run.out / "scores.jsonl", "".join(json.dumps(x, ensure_ascii=False) + "\n" for x in lines))
    # Note: last, so summary.json always stands beside the scores it summarizes.
    write_json(run.out / "summary.json", summary)
    _warn_unused(run, pages, unread)
    say(_closing(summary))
    return summary


def gradable(out: Path) -> None:
    """Refuses a folder grading can't read: one that doesn't exist, or that holds no predictions/."""
    if not out.is_dir():
        raise UsageError(f"no folder at {out}; pass the folder holding predictions/<page_id>.json")
    if not (out / "predictions").is_dir():
        hint = (f"; {out} looks like the predictions/ folder itself: pass its parent, {out.parent}"
                if out.name == "predictions" else "")
        raise UsageError(f"{out} has no predictions/ folder, so nothing was predicted there; a folder to "
                         f"grade holds predictions/<page_id>.json{hint}")


def _graded(run: Run, pages: Sequence[data.Page], cannot: frozenset[str]
            ) -> tuple[list[dict], dict[str, dict[str, int]], list[dict], list[str]]:
    """The score lines of the folder's predictions of `pages`; each suite's pages graded, failed (an output
    the system can produce, missing or null) and pending; the calls its records hold; and the pages whose
    prediction couldn't be read. Writes nothing."""
    keeps, listed = run.records.is_dir(), _listed(run)
    lines, calls, unread, count = [], [], [], {}
    for g in pages:
        c = count.setdefault(g.suite, {"pages": 0, "failed": 0, "pending": 0})
        if keeps and not _tried(run, g.page_id, listed):
            c["pending"] += 1
            continue
        named = f"{g.page_id}.json" in listed
        pred = predicted(run, g.page_id) if named else None
        if named and pred is None: unread.append(g.page_id)
        if (rec := recorded(run, g.page_id)) is not None: calls += rec["calls"]
        c["pages"] += 1
        c["failed"] += any((pred or {}).get(o) is None for o in set(g.outputs) - cannot)
        lines += _grade_page(run, pred or {}, g, _tests(g), cannot)
    return lines, count, calls, unread


def _summary(run: Run, said: Mapping[str, Any], lines: list[dict], count: dict[str, dict[str, int]],
             calls: list[dict]) -> dict:
    """`scorer.summarize` of the lines, beside what graded them, the counts, and the cost; the headline,
    overall and per suite, is None while any page there is pending: a run has one only once it is finished."""
    s = scorer.summarize(lines)
    none = {"headline": None, "score": None}   # a suite every page of which is pending
    per = {k: s["per_suite"].get(k, none) | c for k, c in sorted(count.items())}
    for x in per.values():
        if x["pending"]: x["headline"] = None
    pending = sum(c["pending"] for c in count.values())
    credits = [c["credits"] for c in calls if c.get("credits") is not None]
    return {"run": run.out.name, "provider": run.provider, "settings": said.get("settings", {}), **s,
            "headline": None if pending else s["headline"], "per_suite": per, "scorer": SCORER,
            "pages": sum(c["pages"] for c in count.values()),
            "failed": sum(c["failed"] for c in count.values()), "pending": pending,
            "usd": round(sum(c.get("usd") or 0 for c in calls), 4),
            "credits": round(sum(credits), 4) if credits else None}


def _warn_unused(run: Run, pages: Sequence[data.Page], unread: list[str]) -> None:
    """Logs the predictions grading couldn't use: files named for no page of the manifest (left out), and
    those that couldn't be read as a JSON object (graded as failed). A naming slip (`<page_id>.pdf.json`,
    another case) otherwise shows only as a low score."""
    ids = {f"{g.page_id}.json" for g in pages}
    stray = sorted(n + ("/" if (run.predictions / n).is_dir() else "") for n in _listed(run) - ids)
    if stray:
        log.warning("%s: %d files in predictions/ are named for no page of the manifest, so they were left "
                    "out, e.g. %s; a prediction is predictions/<page_id>.json, named exactly (case too)",
                    run.out, len(stray), stray[:3])
    if unread:
        log.warning("%s: %d predictions couldn't be read as a JSON object, so their pages were graded as "
                    "failed, e.g. %s", run.out, len(unread), unread[:3])


def read_scores(run: Run) -> list[dict]:
    """A run's score lines on disk (scores.jsonl), in file order; [] when it was never graded. A line that
    isn't readable JSON is left out, and logged. A folder that doesn't exist is refused: a mistyped path
    isn't a run with no scores."""
    if not run.out.is_dir():
        raise UsageError(f"no folder at {run.out}; pass a run's folder, which holds scores.jsonl")
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
    """`grade` each run of the plan over the whole manifest; their summaries by run name."""
    _, every = data.read_manifest(p.dataset, p.manifest)
    return {r.out.name: grade(r, every, say) for r in p.runs}


def execute(p: Plan, say: Callable[[str], None] = print) -> dict[str, dict]:
    """Predict, then grade. What was predicted is graded even when predicting failed part way.

    Note: not when it was interrupted (Ctrl-C): whoever stopped it wants it stopped, and
    `--score-only` grades what is there."""
    try:
        if not p.score_only: predict_all(p)
    except Exception:
        grade_all(p, say)
        raise
    return grade_all(p, say)
