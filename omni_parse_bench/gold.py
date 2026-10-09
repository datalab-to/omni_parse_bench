"""The gold: the dataset's pages and their tests. A dataset folder holds

    manifest.parquet       a row per page: page_id, document, suite, doc_path, gt_path
    pages/<page_id>.pdf    the page that gets sent: a one-page PDF, or a .png for an image page
    gold/<page_id>.json    its tests: {"tests": [...]}

A test says what structure it checks (`test_type`), in which output (`output_type`), on what content
(`args`), with what else its runner needs (`settings`); how its claim was established (`derivation`);
and what its content is (`tags`, which grading never reads):

    {"id": "p11_PMC12397559.1_t0_head_17_2", "test_type": "table_cell", "output_type": "html",
     "derivation": "publisher_markup", "tags": ["table", "multi_column"],
     "args": {"cell": {"text": "32 (40.0)", "max_diffs": 0},
              "headings": [{"text": "No. (%)", "max_diffs": 0}]},
     "settings": {}}

`args` maps each role of the test type to one arg, or a list of them. An arg is exactly one of
`{"text", "max_diffs"}`, `{"number"}` or `{"latex"}`: its kind, which says how it is compared. A
`Test` also names its page, the gold file it came from. `load` reads a whole dataset, each test's args
and settings into its runner's parameters; `read` one gold file:

    pages, tests = gold.load("dataset/")
    tests[0].test_type          # "present"
    tests[0].params             # runners.Present(content=runners.Text(text="...", max_diffs=1))
    by_page(tests)[pages[0].page_id]    # the first page's tests
    read("dataset/gold/<page_id>.json")  # one page's tests

A row or test with a missing, unknown or misspelt field, an arg of a kind its role can't compare, a
parameter that doesn't match its type (an empty string counts as a mismatch), a max_diffs that isn't
fewer than its folded text's characters (it would pass on any output), LaTeX that KaTeX can't render
or that renders to nothing (it would fail, or pass, on any output), or a value outside the
vocabulary raises `GoldError` naming it; so, in `load`, does a page with no tests, a gold file
with no manifest row, and an id used twice.
"""
from __future__ import annotations

import collections
import functools
import json
import re
import types
import typing
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, NamedTuple

from omni_parse_bench import equations, normalize, runners, vocab

PAGE_FIELDS = ("page_id", "document", "suite", "doc_path", "gt_path")
FIELDS = ("id", "test_type", "output_type", "derivation", "tags", "args", "settings")
MANIFEST = "manifest.parquet"
_DOC_PATH = re.compile(r"pages/(.+)\.(?:pdf|png)")
KINDS = {"text": ("text", "max_diffs"), "number": ("number",), "latex": ("latex",)}
OPTIONAL = {"text": ("place",)}     # fields an arg of that kind may have
RELATIONS = ("up", "down", "left", "right", "top_heading", "left_heading")
# The roles of each test type's args, the content it compares.
ROLES = {
    "present": ("content",),
    "order": ("before", "after"),
    "repeat": ("content",),
    "table_cell": ("cell", "headings", "section", "row_groups", *RELATIONS),
    "layout_kind": ("content",),
}
LISTS = frozenset({"headings", "row_groups"})   # roles that take a list of args
REQUIRED = {"present": ("content",), "order": ("before", "after"), "repeat": ("content",),
            "table_cell": ("cell",), "layout_kind": ("content",)}
assert set(ROLES) == set(REQUIRED) == set(runners.TYPES) == set(vocab.READS) == set(vocab.FAMILIES)


_LANGUAGE = re.compile(r"[a-z]{3}")    # ISO 639-3
_SCRIPT = re.compile(r"[A-Z][a-z]{3}")   # ISO 15924


class GoldError(ValueError):
    """A manifest row or a test that breaks the dataset's rules."""


class Page(NamedTuple):
    """A row of the manifest; its paths are relative to the dataset folder."""
    page_id: str
    document: str   # the source document: a page's tests pass or fail with its document's
    suite: str
    doc_path: str   # the page file: pages/<page_id>.pdf or .png
    gt_path: str    # its tests: gold/<page_id>.json


class Test(NamedTuple):
    id: str
    page_id: str    # the page whose gold file holds it
    test_type: str
    output_type: str
    derivation: str
    tags: tuple[str, ...]
    params: tuple   # the test type's parameter NamedTuple (`runners.TYPES`)


def load(root: str | Path) -> tuple[tuple[Page, ...], tuple[Test, ...]]:
    """Every page of the dataset folder `root` and every test, checked, each page's tests in its
    gold file's order."""
    try:
        import pyarrow.parquet as pq
    except ImportError:
        raise ImportError("gold.load reads the manifest with pyarrow: "
                          "pip install 'omni-parse-bench[benchmark]'") from None
    root = Path(root).expanduser()
    pages = tuple(page(r) for r in pq.read_table(root / MANIFEST).to_pylist())
    if twice := [i for i, n in collections.Counter(p.page_id for p in pages).items() if n > 1]:
        raise GoldError(f"{len(twice)} page ids are in the manifest more than once, e.g. {twice[:3]}")
    named = {Path(p.gt_path).name for p in pages}
    if stray := sorted(f.name for f in (root / "gold").glob("*.json") if f.name not in named):
        raise GoldError(f"{len(stray)} gold files have no manifest row, e.g. {stray[:3]}")
    tests = tuple(t for p in pages for t in read(root / p.gt_path))
    if twice := [i for i, n in collections.Counter(t.id for t in tests).items() if n > 1]:
        raise GoldError(f"{len(twice)} test ids are used more than once, e.g. {twice[:3]}")
    if empty := sorted({p.page_id for p in pages} - {t.page_id for t in tests}):
        raise GoldError(f"{len(empty)} pages have no tests, e.g. {empty[:3]}; remove them or give them tests")
    return pages, tests


def read(path: str | Path) -> tuple[Test, ...]:
    """One gold file's tests; its name is the page's id."""
    path = Path(path)
    return parse(path.stem, json.loads(path.read_text()))


def parse(page_id: str, doc: Mapping[str, Any]) -> tuple[Test, ...]:
    """A gold file's contents as the page's tests."""
    if unknown := set(doc) - {"tests"}:
        raise GoldError(f"{page_id}: unknown keys {sorted(unknown)}; a gold file holds only 'tests'")
    return tuple(test(page_id, t) for t in doc["tests"])


def by_page(tests: Iterable[Test]) -> dict[str, tuple[Test, ...]]:
    """Each page's tests, in their order, by page id."""
    out: dict[str, list[Test]] = collections.defaultdict(list)
    for t in tests: out[t.page_id].append(t)
    return {p: tuple(ts) for p, ts in out.items()}


def wants(tests: Iterable[Test]) -> frozenset[str]:
    """The output types the tests read: what their page is asked for."""
    return frozenset(t.output_type for t in tests)


def page(r: Mapping[str, Any]) -> Page:
    """One manifest row, checked."""
    where = f"page {r.get('page_id')!r}"
    if missing := [f for f in PAGE_FIELDS if f not in r]:
        raise GoldError(f"{where} lacks {missing}")
    if unknown := [f for f in r if f not in PAGE_FIELDS]:
        raise GoldError(f"{where}: unknown columns {unknown}; a manifest row has {list(PAGE_FIELDS)}")
    if not all(isinstance(r[f], str) and r[f].strip() for f in PAGE_FIELDS):
        raise GoldError(f"{where}: {list(PAGE_FIELDS)} must be non-empty strings")
    if not ((m := _DOC_PATH.fullmatch(r["doc_path"])) and m[1] == r["page_id"]):
        raise GoldError(f"{where}: doc_path must be pages/<page_id>.pdf or .png, not {r['doc_path']!r}")
    if r["gt_path"] != f"gold/{r['page_id']}.json":
        raise GoldError(f"{where}: gt_path must be gold/<page_id>.json, not {r['gt_path']!r}")
    return Page(r["page_id"], r["document"], r["suite"], r["doc_path"], r["gt_path"])


def test(page_id: str, t: Mapping[str, Any]) -> Test:
    """One test of a page's gold file, checked."""
    where = f"{page_id}: test {t.get('id')!r}"
    if missing := [f for f in FIELDS if f not in t]:
        raise GoldError(f"{where} lacks {missing}")
    if unknown := [f for f in t if f not in FIELDS]:
        raise GoldError(f"{where}: unknown fields {unknown}; a test has {list(FIELDS)}")
    if not (isinstance(t["id"], str) and t["id"].strip()):
        raise GoldError(f"{where}: id must be a non-empty string")
    test_type, output_type = t["test_type"], t["output_type"]
    if test_type not in runners.TYPES:
        raise GoldError(f"{where}: unknown test_type {test_type!r}; known: {sorted(runners.TYPES)}")
    if output_type != vocab.READS[test_type]:
        raise GoldError(f"{where}: {test_type} reads {vocab.READS[test_type]!r}, not {output_type!r}")
    if t["derivation"] not in vocab.DERIVATIONS:
        raise GoldError(f"{where}: unknown derivation {t['derivation']!r}; known: {vocab.DERIVATIONS}")
    if not isinstance(t["tags"], list) or not all(isinstance(x, str) for x in t["tags"]):
        raise GoldError(f"{where}: tags must be a list of strings, not {t['tags']!r:.80}")
    if unknown := [x for x in t["tags"] if not _tag(x)]:
        raise GoldError(f"{where}: unknown tags {unknown}; a tag is one of {[*vocab.ROLES, *vocab.YES_NO]}, "
                        "a language (ISO 639-3, e.g. eng) or a script (ISO 15924, e.g. Latn)")
    params = _params(where, test_type, t["args"], t["settings"])
    for name, hint in _hints(type(params)).items():
        if not _typed(getattr(params, name), hint):
            raise GoldError(f"{where}: {name}={getattr(params, name)!r:.80} isn't a {hint}")
    if test_type in runners.VALID and not (rule := runners.VALID[test_type])[0](params):
        raise GoldError(f"{where}: {rule[1]}")
    return Test(t["id"], page_id, test_type, output_type, t["derivation"], tuple(t["tags"]), params)


def _tag(x: str) -> bool:
    """A vocabulary tag, a language code or a script code."""
    return x in vocab.ROLES or x in vocab.YES_NO or bool(_LANGUAGE.fullmatch(x) or _SCRIPT.fullmatch(x))


def _params(where: str, test_type: str, args: Any, settings: Any) -> Any:
    """The runner's parameters from a test's args and settings."""
    if not isinstance(args, dict) or not isinstance(settings, dict):
        raise GoldError(f"{where}: args and settings must be objects")
    roles = ROLES[test_type]
    if unknown := [r for r in args if r not in roles]:
        raise GoldError(f"{where}: {test_type} has no role {unknown}; its roles: {list(roles)}")
    if missing := [r for r in REQUIRED[test_type] if r not in args]:
        raise GoldError(f"{where}: {test_type} needs args {missing}")
    for r, v in args.items():
        if (r in LISTS) != isinstance(v, list):
            raise GoldError(f"{where}: {r} takes {'a list of args' if r in LISTS else 'one arg'}")
        for a in v if isinstance(v, list) else [v]:
            match _kind(where, r, a):
                case "text": _diffs(where, r, a)
                case "latex": _renders(where, r, a)
    def text(r: str) -> str:
        if (k := _kind(where, r, args[r])) != "text":
            raise GoldError(f"{where}: {test_type}'s {r} compares text only, not {k}")
        return args[r]["text"]
    def diffs(rs: list[str]) -> int:
        ds = {a["max_diffs"] for r in rs for a in (args[r] if isinstance(args[r], list) else [args[r]])}
        if len(ds) != 1: raise GoldError(f"{where}: its args must share max_diffs, not {sorted(ds)}")
        return ds.pop()
    try:
        match test_type:
            case "present":
                _no(where, settings)
                return runners.Present(_arg(where, "content", args["content"]))
            case "order":
                _no(where, settings)
                return runners.Order(text("before"), text("after"), diffs(["before", "after"]))
            case "repeat":
                if diffs(["content"]) != 0:
                    raise GoldError(f"{where}: repeat counts exact text: max_diffs must be 0")
                return runners.Repeat(text("content"), **settings)
            case "layout_kind":
                if set(settings) != {"kind"}:
                    raise GoldError(f"{where}: layout_kind's settings are exactly {{kind}}")
                return runners.LayoutKind(_arg(where, "content", args["content"]), settings["kind"])
            case "table_cell":
                _no(where, settings)
                for r in args:
                    for a in args[r] if r in LISTS else [args[r]]:
                        if "text" not in a: raise GoldError(f"{where}: table_cell's {r} compares text only")
                return runners.TableCell(
                    text("cell"), {r: text(r) for r in RELATIONS if r in args}, diffs(list(args)),
                    tuple(_frozen([a["text"] for a in args.get("headings", [])])),
                    text("section") if "section" in args else None,
                    tuple(_frozen([a["text"] for a in args.get("row_groups", [])])))
            case _:
                raise AssertionError(test_type)
    except TypeError as e:
        raise GoldError(f"{where}: {e}") from None


def _arg(where: str, role: str, a: Any) -> runners.Arg:
    """An arg as the runner's content: its kind is its key, never guessed from its value."""
    match _kind(where, role, a):
        case "text": return runners.Text(a["text"], a["max_diffs"], _place(where, role, a.get("place", [])))
        case "number": return runners.Number(a["number"])
        case _: return runners.Latex(a["latex"])


def _kind(where: str, role: str, a: Any) -> str:
    """The kind of an arg (text, number or latex), checking it has that kind's fields and no others."""
    k = next((k for k, fs in KINDS.items()
              if isinstance(a, dict) and set(fs) <= set(a) <= {*fs, *OPTIONAL.get(k, ())}), None)
    if k is None:
        raise GoldError(f"{where}: {role}={a!r:.80} isn't an arg: the fields {{text, max_diffs[, place]}}, "
                        f"{{number}} or {{latex}}")
    return k


def _diffs(where: str, role: str, a: Mapping[str, Any]) -> None:
    """A text arg's max_diffs: a whole number of edits, fewer than its folded text has characters."""
    text, d = a["text"], a["max_diffs"]
    if not (isinstance(text, str) and (n := len(normalize.fold(text)))):
        raise GoldError(f"{where}: {role}'s text must be a string with something left after folding, "
                        f"not {text!r:.80}")
    # Note: at `n` edits any output holds the text, so the test would pass on anything.
    if not (isinstance(d, int) and not isinstance(d, bool) and 0 <= d < n):
        raise GoldError(f"{where}: {role}'s max_diffs must be a whole number from 0 to {n - 1} (its folded "
                        f"text has {n} characters), not {d!r}")


def _renders(where: str, role: str, a: Mapping[str, Any]) -> None:
    """A latex arg's equation: KaTeX renders it to at least one symbol."""
    tex = a["latex"]
    if not (isinstance(tex, str) and tex.strip()):
        raise GoldError(f"{where}: {role}'s latex must be a non-empty string, not {tex!r:.80}")
    # Note: a test whose LaTeX doesn't render fails on every output, and one rendering to no symbol
    # ("\\quad") passes on every output (`equations.appears`).
    if (got := equations.symbols(tex, True)) is None:
        raise GoldError(f"{where}: {role}'s latex {tex!r:.80} doesn't render in KaTeX; fix its LaTeX")
    if not got:
        raise GoldError(f"{where}: {role}'s latex {tex!r:.80} renders to nothing (only spacing or "
                        "invisible marks); give it the equation's symbols or remove the test")


def _place(where: str, role: str, place: Any) -> tuple[tuple[float, float, float, float], ...]:
    """An arg's place: a box `[x0, y0, x1, y1]` per line, fractions of the page as displayed."""
    if not isinstance(place, list) or not all(
            isinstance(b, list) and len(b) == 4
            and all(isinstance(x, (int, float)) and 0 <= x <= 1 for x in b)
            and b[0] < b[2] and b[1] < b[3] for b in place):
        raise GoldError(f"{where}: {role}'s place must be a list of [x0, y0, x1, y1] boxes from 0 to 1, "
                        f"not {place!r:.80}")
    return tuple(tuple(float(x) for x in b) for b in place)


def _no(where: str, settings: Mapping[str, Any]) -> None:
    if settings: raise GoldError(f"{where}: no settings expected, got {sorted(settings)}")


@functools.cache
def _hints(Params: type) -> dict[str, Any]:
    return typing.get_type_hints(Params, globalns=vars(runners))


def _typed(v: Any, hint: Any) -> bool:
    """Whether `v` fits `hint`; strings must also be non-empty."""
    origin, args = typing.get_origin(hint), typing.get_args(hint)
    if origin is typing.Literal: return v in args
    if origin in (typing.Union, types.UnionType): return any(_typed(v, a) for a in args)
    if origin is tuple:
        if not isinstance(v, tuple): return False
        if len(args) == 2 and args[1] is Ellipsis: return all(_typed(x, args[0]) for x in v)
        return len(v) == len(args) and all(_typed(x, a) for x, a in zip(v, args, strict=True))
    if origin is dict:
        return isinstance(v, dict) and all(_typed(k, args[0]) and _typed(x, args[1]) for k, x in v.items())
    if hint is type(None): return v is None
    if isinstance(hint, type) and issubclass(hint, tuple) and hasattr(hint, "_fields"):
        return isinstance(v, hint) and all(_typed(getattr(v, f), h) for f, h in _hints(hint).items())
    if hint is float: return isinstance(v, (int, float)) and not isinstance(v, bool)
    if hint is int: return isinstance(v, int) and not isinstance(v, bool)
    if hint is str: return isinstance(v, str) and bool(v.strip())
    return isinstance(v, hint)


def _frozen(v: Any) -> Any:
    """JSON lists as tuples, so a runner can't change its parameters."""
    if isinstance(v, list):
        return tuple(_frozen(x) for x in v)
    return v
