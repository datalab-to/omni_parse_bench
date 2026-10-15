"""The dataset: its pages, read from a folder or downloaded from Hugging Face. A dataset folder holds

    manifest.parquet       a row per page: page_id, document, suite, doc_path, gt_path, outputs
    pages/<page_id>.pdf    the page that gets sent: a one-page PDF, or a .png for an image page
    gold/<page_id>.json    its tests: {"tests": [...]}, read by `scorer.gold` (`gold.py` says what a test is)

A page is a manifest row (`Page`) whose paths are full local paths, so a page says where its file and
its gold are without the dataset beside it. The functions over a dataset:

    download_dataset(dataset)    a local copy of the whole dataset; a local folder as it is
    read_manifest(dataset)       the folder and every page, checked; reads the manifest alone
    select(pages, ...)           the pages to run: by suite or id, sampled, limited
    check_dataset(dataset)       every page and every test, checked across the dataset, for publishing
    dataset_id(dataset)          what a run's dataset is, whatever its revision

`dataset` is a folder's path or `hf://datasets/<repo>[@<revision>]`. `read_manifest` and
`check_dataset` read once per process.
"""
from __future__ import annotations

import collections
import dataclasses
import functools
import re
import time
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from omni_parse_bench import gold, scorer, vocab

HF_PREFIX = "hf://datasets/"
DEFAULT_DATASET = "hf://datasets/datalab-to/omni_parse_bench"
DOWNLOAD_ATTEMPTS = 5
MANIFEST = "manifest.parquet"
PAGE_FIELDS = ("page_id", "document", "suite", "doc_path", "gt_path", "outputs")
NAMES = PAGE_FIELDS[:-1]    # the fields that are names and paths: non-empty strings
OUTPUTS = frozenset(vocab.READS.values())     # the output types a test can read: html, blocks
# Note: the dataset's commits before 41131f2 (175cc91, 1c35a52) have no outputs column; omni-parse-bench
# 0.1.x reads them.
OLD_DATASET = (
    "the dataset at {root} is from before omni-parse-bench 0.1.2: its manifest has no 'outputs' column "
    "(the dataset's commits 1c35a52 and earlier). Use the current dataset:\n"
    "  - from Hugging Face: drop the @<commit> pin, i.e. --dataset hf://datasets/datalab-to/omni_parse_bench;\n"
    "  - a downloaded copy: download it again: "
    "hf download datalab-to/omni_parse_bench --repo-type dataset --local-dir <folder>; or\n"
    "  - to keep this copy, use the omni-parse-bench made for it: pip install 'omni-parse-bench==0.1.1'")
_DOC_PATH = re.compile(r"pages/(.+)\.(?:pdf|png)")


@dataclasses.dataclass(frozen=True)
class Page:
    """A row of the manifest, its paths full local paths (`read_manifest` resolves the manifest's, which are
    relative to the dataset folder), so a page's file and tests are read from the page alone.

    `extra` holds the row's other columns: omni-parse-bench reads none of them, so a dataset can carry
    columns of its own (a language, a tag, another gold) for scorers of its own. Treat it as read-only.
    A frozen dataclass rather than a NamedTuple so each page gets its own `extra`; a copy with a field
    changed is `dataclasses.replace(page, ...)`. A dict makes a page unhashable."""
    page_id: str
    document: str   # the source document: a page's tests pass or fail with its document's
    suite: str
    doc_path: str   # the page file: <dataset>/pages/<page_id>.pdf or .png
    gt_path: str    # its tests: <dataset>/gold/<page_id>.json
    outputs: tuple[str, ...]    # what to predict: the output types its tests read (`gold.wants`), sorted
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)   # the manifest's other columns

    @property
    def id(self) -> str:
        """The page's id, by the name every benchmark's rows share (oeb's `Doc.id` is its doc_id)."""
        return self.page_id


def download_dataset(dataset: str | Path) -> Path:
    """A dataset as a local folder: a path as given, or a Hugging Face dataset downloaded whole, at one
    commit, into Hugging Face's cache (so a second call downloads nothing). Its folder's name is that
    commit.

    Note: the whole dataset (opb's is 1.5 GB), so its pages and its gold are always one commit's.
    Fetching each page when it is first predicted would let a `--limit` run download only its pages;
    that is an optimization for later.
    """
    if not str(dataset).startswith(HF_PREFIX):
        root = Path(dataset).expanduser()
        if not (root / MANIFEST).exists():
            raise FileNotFoundError(f"no {MANIFEST} in {root}; pass --dataset a dataset folder "
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
                                          max_workers=4))
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


@functools.cache
def read_manifest(dataset: str | Path) -> tuple[Path, tuple[Page, ...]]:
    """The dataset's folder (`download_dataset`) and its pages, checked, each with what to predict for it,
    and its file and gold as full paths. It reads the manifest alone: no gold file is opened. Its columns
    must include `PAGE_FIELDS`; any other column is carried on each page's `extra`, never refused."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("omni-parse-bench reads the manifest with pyarrow: "
                          "pip install 'omni-parse-bench[benchmark]'") from None
    root = download_dataset(dataset).resolve()
    table = pq.read_table(root / MANIFEST)
    if "outputs" not in table.column_names:
        raise gold.GoldError(OLD_DATASET.format(root=root))
    rows = tuple(dataclasses.replace(p := page(r), doc_path=str(root / p.doc_path),
                                     gt_path=str(root / p.gt_path)) for r in table.to_pylist())
    if twice := [i for i, n in collections.Counter(p.page_id for p in rows).items() if n > 1]:
        raise gold.GoldError(f"{len(twice)} page ids are in the manifest more than once, e.g. {twice[:3]}")
    return root, rows


def select(pages: Sequence[Page], suites: list[str] | None = None, limit: int = 0,
           sample: int = 0, only: frozenset[str] | None = None) -> tuple[Page, ...]:
    """The pages of `pages` (a dataset's, from `read_manifest`) to run, in their order, filtered by suite
    and by `only` (page ids, each of which must be among them), and limited.

    `sample` picks that many pages spread over every suite: suites in turn, each page evenly spaced
    within its suite, so a smoke test sees every kind of page and the same pages each time."""
    rows = tuple(pages)
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
    return rows[:limit] if limit else rows


@functools.cache
def check_dataset(dataset: str | Path) -> tuple[tuple[Page, ...], tuple[gold.Test, ...]]:
    """Every page of the dataset and every test, checked, each page's tests in its gold file's order: what
    publishing a dataset checks, and `opb tests` writes. A page's `outputs` is checked against its tests,
    and the dataset as a whole: a gold file with no manifest row, a test id used twice, and a page with
    no tests are refused. Grading needs none of it: it reads each page's tests when it grades the page."""
    root, rows = read_manifest(str(dataset))
    named = {Path(p.gt_path).name for p in rows}
    if stray := sorted(f.name for f in (root / "gold").glob("*.json") if f.name not in named):
        raise gold.GoldError(f"{len(stray)} gold files have no manifest row, e.g. {stray[:3]}")
    every = tuple(t for p in rows for t in scorer.gold(p))
    if twice := [i for i, n in collections.Counter(t.id for t in every).items() if n > 1]:
        raise gold.GoldError(f"{len(twice)} test ids are used more than once, e.g. {twice[:3]}")
    if empty := sorted({p.page_id for p in rows} - {t.page_id for t in every}):
        raise gold.GoldError(f"{len(empty)} pages have no tests, e.g. {empty[:3]}; remove them or give "
                             "them tests")
    return rows, every


def page(r: Mapping[str, Any]) -> Page:
    """One manifest row, checked."""
    where = f"page {r.get('page_id')!r}"
    if missing := [f for f in PAGE_FIELDS if f not in r]:
        raise gold.GoldError(f"{where} lacks {missing}")
    if not all(isinstance(r[f], str) and r[f].strip() for f in NAMES):
        raise gold.GoldError(f"{where}: {list(NAMES)} must be non-empty strings")
    if not ((m := _DOC_PATH.fullmatch(r["doc_path"])) and m[1] == r["page_id"]):
        raise gold.GoldError(f"{where}: doc_path must be pages/<page_id>.pdf or .png, not {r['doc_path']!r}")
    if r["gt_path"] != f"gold/{r['page_id']}.json":
        raise gold.GoldError(f"{where}: gt_path must be gold/<page_id>.json, not {r['gt_path']!r}")
    outputs = r["outputs"]
    if (not isinstance(outputs, list | tuple) or not outputs or not set(outputs) <= OUTPUTS
            or len(set(outputs)) != len(outputs)):
        raise gold.GoldError(f"{where}: outputs must be a non-empty list of distinct output types from "
                             f"{sorted(OUTPUTS)}, not {outputs!r}")
    extra = {k: v for k, v in r.items() if k not in PAGE_FIELDS}
    return Page(r["page_id"], r["document"], r["suite"], r["doc_path"], r["gt_path"], tuple(sorted(outputs)),
                extra)
