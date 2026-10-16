"""The dataset: its pages, read from a folder or downloaded from Hugging Face. A dataset folder holds

    manifest.parquet       a row per page: page_id, document, suite, doc_path, gt_path, outputs
    pages/...              the page files that get sent: one-page PDFs, or .png for image pages
    gold/<page_id>.json    each page's tests: {"tests": [...]}, read by the scorer (`scorers.unit_tests.gold`)

A page is a manifest row (`Page`) whose paths are full local paths, so a page says where its file and
its gold are without the dataset beside it. The functions over a dataset:

    download_dataset(dataset)    a local copy of the whole dataset; a local folder as it is
    read_manifest(dataset, ...)  the folder and every page of a manifest, checked; reads the manifest alone
    select(pages, ...)           the pages to run: by suite or id, sampled, limited
    dataset_id(dataset)          what a run's dataset is, whatever its revision
    commit(dataset, root)        the commit a Hugging Face dataset was read at; None for a folder
    normal(manifest)             a manifest's path in its dataset, spelled one way

`dataset` is a folder's path or `hf://datasets/<repo>[@<revision>]`. `read_manifest` reads once per
process. Checking every test of a dataset is the scorer's, `scorers.unit_tests.check(pages)`.
"""
from __future__ import annotations

import dataclasses
import functools
import logging
import os
import time
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

from omni_parse_bench import vocab
from omni_parse_bench import errors

log = logging.getLogger(__name__)

HF_PREFIX = "hf://datasets/"
DEFAULT_DATASET = "hf://datasets/datalab-to/omni_parse_bench"
DOWNLOAD_ATTEMPTS = 5
MANIFEST = "manifest.parquet"
PAGE_FIELDS = ("page_id", "document", "suite", "doc_path", "gt_path", "outputs")
NAMES = ("page_id", "document", "doc_path", "gt_path")    # names and paths: non-empty strings
NO_SUITE = "other"          # the suite of a page whose manifest gives none (null or "")
OUTPUTS = frozenset(vocab.READS.values())     # the output types a test can read: html, blocks


# Note: the dataset's commits before 41131f2 (175cc91, 1c35a52) have no outputs column; omni-parse-bench
# 0.1.x reads them.
OLD_DATASET = (
    "the dataset at {root} is from before omni-parse-bench 0.1.2: its manifest has no 'outputs' column "
    "(the dataset's commits 1c35a52 and earlier). Use the current dataset:\n"
    "  - from Hugging Face: drop the @<commit> pin, i.e. --dataset "
    "hf://datasets/datalab-to/omni_parse_bench;\n  - a downloaded copy: download it again: "
    "hf download datalab-to/omni_parse_bench --repo-type dataset --local-dir <folder>; or\n"
    "  - to keep this copy, use the omni-parse-bench made for it: pip install 'omni-parse-bench==0.1.1'")


class ManifestError(errors.UsageError):
    """A manifest, or a row of one, that breaks the dataset's rules; the message names it and the fix."""


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
    doc_path: Path  # the page file, a .pdf or .png
    gt_path: Path   # its tests: <dataset>/.../<page_id>.json
    outputs: tuple[str, ...]    # what to predict: the output types its tests read (`gold.wants`), sorted
    extra: dict[str, Any] = dataclasses.field(default_factory=dict)   # the manifest's other columns

    @property
    def id(self) -> str:
        """The page's id, by the name every benchmark's rows share (oeb's `Doc.id` is its doc_id)."""
        return self.page_id


def _hf_dataset(dataset: str | Path) -> tuple[str, str | None] | None:
    """The repo and revision `dataset` addresses, or None when it is a folder on disk."""
    form = f"{HF_PREFIX}<org>/<name>[@<revision>], e.g. {DEFAULT_DATASET}"
    s = str(dataset)
    if isinstance(dataset, Path) and s.startswith("hf:"):
        raise errors.UsageError(f"the dataset {s!r} was made a Path, which folds the '//' out of an address. "
                                f"Pass it as a str: {form}")
    if s.startswith("hf:") and not s.startswith("hf://"):
        raise errors.UsageError(f"{s!r} looks like a Hugging Face address with a slash missing. Write it as "
                                f"{form}")
    if not s.startswith("hf://"): return None
    org, _, name = s.removeprefix(HF_PREFIX).partition("/")
    name, at, revision = name.partition("@")
    if not s.startswith(HF_PREFIX) or not org or not name or "/" in name or (at and not revision):
        raise errors.UsageError(f"{s!r} does not name a Hugging Face dataset. Write it as {form}")
    return f"{org}/{name}", revision or None


def download_dataset(dataset: str | Path) -> Path:
    """A dataset as a local folder: a path as given, or a Hugging Face dataset downloaded whole, at one
    commit, into Hugging Face's cache (so a second call downloads nothing). Its folder's name is that
    commit.

    Note: the whole dataset (opb's is 1.5 GB), so its pages and its gold are always one commit's.
    Fetching each page when it is first predicted would let a `--limit` run download only its pages;
    that is an optimization for later.
    """
    if (at := _hf_dataset(dataset)) is None:
        root = Path(dataset).expanduser()
        if not root.is_dir():
            raise errors.UsageError(f"no dataset folder at {root}; pass --dataset a dataset folder "
                                    f"or {HF_PREFIX}<org>/<name>")
        return root
    from huggingface_hub import errors as hf_errors
    import huggingface_hub

    repo, revision = at
    log.info("reading %s from the Hugging Face cache, downloading what it lacks", dataset)
    # Note: thousands of small files; the Hub drops some requests under that load, and a download
    # picks up where the last left off, so it is simply tried again. A missing repo, revision or
    # access, or no network with nothing cached, is the same on every attempt, so it fails at once.
    for attempt in range(DOWNLOAD_ATTEMPTS):
        try:
            return Path(huggingface_hub.snapshot_download(repo, repo_type="dataset", revision=revision,
                                                          max_workers=4))
        except (hf_errors.RepositoryNotFoundError, hf_errors.GatedRepoError,
                hf_errors.RevisionNotFoundError) as exc:
            raise errors.UsageError(f"can't read dataset {dataset}: {type(exc).__name__}. Check the repo and "
                                    "revision, and that you're logged in with access (huggingface-cli login)"
                                    ) from None
        except (hf_errors.LocalEntryNotFoundError, hf_errors.OfflineModeIsEnabled) as exc:
            # Note: offline by the user's own setting, connecting changes nothing; unsetting it does.
            how = ("HF_HUB_OFFLINE is set; unset it" if os.environ.get("HF_HUB_OFFLINE", "") not in ("", "0")
                   else "the Hub can't be reached; connect")
            raise errors.UsageError(f"can't read dataset {dataset}: it isn't in the Hugging Face cache, and "
                                    f"{how}, or pass --dataset a folder ({type(exc).__name__})") from None
        except hf_errors.HfHubHTTPError as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (401, 403):
                raise errors.UsageError(f"can't read dataset {dataset}: HTTP {status}. Log in with access to "
                                        "it (huggingface-cli login)") from None
            if attempt == DOWNLOAD_ATTEMPTS - 1: raise
            log.warning("downloading %s failed (HTTP %s); trying again in %ds", dataset, status,
                        30 * (attempt + 1))
        except Exception as exc:
            if attempt == DOWNLOAD_ATTEMPTS - 1: raise
            log.warning("downloading %s failed (%s: %s); trying again in %ds", dataset, type(exc).__name__,
                        str(exc)[:200], 30 * (attempt + 1))
        time.sleep(30 * (attempt + 1))
    raise AssertionError("unreachable")


def dataset_id(dataset: str | Path) -> str:
    """What a run's dataset is, whatever revision: the repo of an `hf://` dataset, or a folder's path."""
    if (at := _hf_dataset(dataset)) is not None: return f"{HF_PREFIX}{at[0]}"
    return str(Path(dataset).expanduser().resolve())


def normal(manifest: str) -> str:
    """A manifest's path in its dataset, spelled one way: `./manifest.parquet` is `manifest.parquet`."""
    return PurePosixPath(manifest).as_posix()


def commit(dataset: str | Path, root: Path) -> str | None:
    """The commit `dataset` was read at, its downloaded folder `root`'s name; None for a folder."""
    return root.name if _hf_dataset(dataset) is not None else None


@functools.cache
def read_manifest(dataset: str | Path, manifest: str = MANIFEST) -> tuple[Path, tuple[Page, ...]]:
    """The dataset's folder (`download_dataset`) and its pages, checked, each with what to predict for it,
    and its file and gold as full paths. It reads the manifest alone: no gold file is opened. Its columns
    must include `PAGE_FIELDS`; any other column is carried on each page's `extra`, never refused."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("omni-parse-bench reads the manifest with pyarrow: "
                          "pip install 'omni-parse-bench[benchmark]'") from None
    manifest = normal(manifest)
    if Path(manifest).is_absolute() or ".." in Path(manifest).parts:
        raise ManifestError(f"--manifest {manifest} must be a path inside the dataset, relative to it, e.g. "
                            "manifests/sample.parquet: pass --dataset the dataset's folder, and --manifest "
                            "the manifest's path in there")
    root = download_dataset(dataset).resolve()
    if not (root / manifest).is_file():
        # Note: a manifest is a path inside the dataset; one given as a path on disk is a common slip.
        here = (f" {manifest} is a file here, but a manifest is a path inside the dataset: pass --dataset "
                f"{Path(manifest).parent} --manifest {Path(manifest).name}." if Path(manifest).is_file()
                else "")
        raise ManifestError(f"no manifest {manifest} in {root}.{here} A dataset holds manifest.parquet, and "
                            "may hold others (e.g. manifests/sample.parquet), each naming its pages; pass "
                            "--manifest one, a path inside the dataset")
    table = pq.read_table(root / manifest)
    if "outputs" not in table.column_names:
        raise ManifestError(OLD_DATASET.format(root=root))
    rows = tuple(dataclasses.replace(p := _page(r), doc_path=root / p.doc_path, gt_path=root / p.gt_path)
                 for r in table.to_pylist())
    if not rows:
        raise ManifestError(f"the manifest {manifest} in {root} names no pages")
    # Note: ignoring case, because an id names files, and two ids that differ only in case name one file
    # on a case-insensitive disk (macOS, Windows).
    by: dict[str, list[str]] = {}
    for p in rows: by.setdefault(p.page_id.casefold(), []).append(p.page_id)
    if twice := [ids for ids in by.values() if len(ids) > 1]:
        raise ManifestError(f"page ids in the manifest more than once (ignoring case, since each names "
                            f"files): {errors.counted(len(twice), 'id')}, e.g. {twice[:3]}")
    return root, rows


def select(pages: Sequence[Page], suites: Iterable[str] | None = None, limit: int = 0,
           sample: int = 0, only: Iterable[str] | None = None) -> tuple[Page, ...]:
    """The pages of `pages` (a dataset's, from `read_manifest`) to run, in their order, filtered by suite
    and by `only` (page ids, each of which must be among them), and limited.

    `sample` picks that many pages spread over every suite: suites in turn, each page evenly spaced
    within its suite, so a smoke test sees every kind of page and the same pages each time."""
    suites, only = _names(suites, "suites") or None, _names(only, "only")
    for name, n in (("limit", limit), ("sample", sample)):
        if isinstance(n, bool) or not isinstance(n, int):
            raise TypeError(f"{name} is a whole number, not {n!r}")
        if n < 0:
            raise errors.UsageError(f"--{name} is {n}, but it counts pages, so it can't be negative; 0 is no "
                                    "limit")
    rows = tuple(pages)
    known = {r.suite for r in rows}
    if suites is not None and (bad := sorted(suites - known)):
        raise errors.UsageError(f"unknown suites {bad}; the dataset's suites are {sorted(known)}")
    rows = tuple(r for r in rows if suites is None or r.suite in suites)
    if only is not None:
        if bad := sorted(only - {r.page_id for r in rows}):
            where = " (or its suites)" if suites else ""
            raise errors.UsageError(f"pages asked for that aren't in the dataset{where}: "
                                    f"{errors.counted(len(bad), 'page')}, e.g. {bad[:3]}; nothing has been "
                                    "run")
        rows = tuple(r for r in rows if r.page_id in only)
    if sample and rows:
        by: dict[str, list] = {}
        for r in rows: by.setdefault(r.suite, []).append(r)
        k = -(-sample // len(by))
        spread = [[xs[i * len(xs) // min(k, len(xs))] for i in range(min(k, len(xs)))] for xs in by.values()]
        turns = [x for i in range(k) for xs in spread if i < len(xs) for x in [xs[i]]]
        chosen = {r.page_id for r in turns[:sample]}
        rows = tuple(r for r in rows if r.page_id in chosen)
    return rows[:limit] if limit else rows


def _names(xs: Iterable[str] | None, what: str) -> frozenset[str] | None:
    """`xs` as a set, read once (a generator is a one-pass iterable); a bare str is refused, since iterated it
    is one-letter names."""
    if isinstance(xs, str):
        raise TypeError(f"{what} is a list of names, not the string {xs!r}; pass [{xs!r}]")
    return None if xs is None else frozenset(xs)


def _page(r: Mapping[str, Any]) -> Page:
    """One manifest row, checked."""
    where = f"page {r.get('page_id')!r}"
    if missing := [f for f in PAGE_FIELDS if f not in r]:
        raise ManifestError(f"{where} lacks {missing}")
    if not all(isinstance(r[f], str) and r[f].strip() for f in NAMES):
        raise ManifestError(f"{where}: {list(NAMES)} must be non-empty strings")
    if r["page_id"] in (".", "..") or Path(r["page_id"]).name != r["page_id"]:
        raise ManifestError(f"{where}: page_id must be a filename, one path component: it names the page's "
                            "prediction, its record and its gold")
    if r["suite"] is not None and not isinstance(r["suite"], str):
        raise ManifestError(f"{where}: suite must be a string, or null for {NO_SUITE!r}, not {r['suite']!r}")
    if not _inside(r["doc_path"], (".pdf", ".png")):
        raise ManifestError(f"{where}: doc_path must be a path inside the dataset to a .pdf or .png, "
                            f"e.g. pages/scan.pdf (any name), not {r['doc_path']!r}")
    if not _inside(r["gt_path"], (".json",), r["page_id"]):
        raise ManifestError(f"{where}: gt_path must be a path inside the dataset named <page_id>.json, "
                            f"e.g. gold/{r['page_id']}.json, not {r['gt_path']!r}")
    outputs = r["outputs"]
    if (not isinstance(outputs, list | tuple) or not outputs or not set(outputs) <= OUTPUTS
            or len(set(outputs)) != len(outputs)):
        raise ManifestError(f"{where}: outputs must be a non-empty list of distinct output types from "
                             f"{sorted(OUTPUTS)}, not {outputs!r}")
    extra = {k: v for k, v in r.items() if k not in PAGE_FIELDS}
    suite = r["suite"] if (r["suite"] or "").strip() else NO_SUITE
    return Page(r["page_id"], r["document"], suite, r["doc_path"], r["gt_path"], tuple(sorted(outputs)),
                extra)


def _inside(path: str, suffixes: tuple[str, ...], stem: str | None = None) -> bool:
    """Whether `path` is relative, stays inside the dataset, ends in one of `suffixes`, and, given `stem`,
    is named `<stem><suffix>`.

    Note: a gold is named for its page, in any folder (gold/, transcripts/, ...), so one dataset's pages
    can carry golds of several kinds, one manifest each, and no two pages share one. An input is not:
    several pages may read one file."""
    p = Path(path)
    return (not p.is_absolute() and ".." not in p.parts and p.suffix in suffixes
            and (stem is None or p.stem == stem))
