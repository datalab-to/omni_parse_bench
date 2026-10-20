"""The line between a system's failure and our bug: an answer is read inside
`omni_bench_core.adapter.reading`.

The core's one rule: a page counts 0 only when code raises `SystemFailed` on purpose, and `reading` is how
an adapter says so for a malformed answer. Inside `reading`, an answer that can't be read fails one page and
the run goes on. Anywhere else in an adapter's call, an exception is a bug, and stops the run. So every place
that reads what a system sent back while calling it (a job id, a status, a server's answer) must sit inside
`reading`.

The guard walks each provider module, and `harness/http.py`, from the functions that call a system (`call`,
`send`, and http's `post` and `parse`) through the module's own helpers they call. In those it fails on:

- a `.json()` call outside a `reading` block; and
- a subscript of a name bound from an answer (`.json()`, `json_object`, `http.parse`, `http.post`, `chat`)
  outside a `reading` block.

It is a guard, not a type checker. `parse` isn't walked: it reads the answer throughout, so it states its
failures itself, by raising `SystemFailed` or reading the system's structures inside `reading`; anything else
it raises stops the run as a bug, with the answer kept unread (tests/test_flow.py).
"""
from __future__ import annotations

import ast
import dataclasses
from pathlib import Path
from typing import ClassVar

import pytest

pytest.importorskip("httpx")
pytest.importorskip("openai")

from omni_bench_core import adapter as core  # noqa: E402

from omni_parse_bench import harness  # noqa: E402
from omni_parse_bench.harness import contract  # noqa: E402

HARNESS = Path(harness.__file__).parent
MODULES = sorted([*(HARNESS / "providers").glob("*.py"), HARNESS / "http.py"])
ANSWERS = {"json", "json_object", "parse", "post", "chat"}   # calls whose result is a system's answer


def roots(path: Path) -> set[str]:
    """The functions of a module that call a system."""
    return {"post", "parse"} if path.name == "http.py" else {"call", "send"}


def reached(tree: ast.Module, start: set[str]) -> list[ast.FunctionDef]:
    """The module's functions reached from `start` through calls to the module's own functions."""
    defs = {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    seen, todo = set(), [n for n in start if n in defs]
    while todo:
        if (name := todo.pop()) in seen: continue
        seen.add(name)
        todo += [c.func.id for c in ast.walk(defs[name]) if isinstance(c, ast.Call)
                 and isinstance(c.func, ast.Name) and c.func.id in defs and c.func.id != "parse"]
    return [defs[n] for n in seen]


def is_reading(node: ast.With) -> bool:
    calls = [i.context_expr for i in node.items if isinstance(i.context_expr, ast.Call)]
    return any(getattr(c.func, "attr", None) == "reading" for c in calls)


def answer_call(node: ast.AST) -> bool:
    return any(isinstance(c, ast.Call) and getattr(c.func, "attr", getattr(c.func, "id", None)) in ANSWERS
               for c in ast.walk(node))


def outside(fn: ast.FunctionDef) -> list[str]:
    """Each read of an answer in `fn` that isn't inside a `reading` block, as `line: what`."""
    bound = {t.id for n in ast.walk(fn) for t in (n.targets if isinstance(n, ast.Assign) else
             [n.target] if isinstance(n, ast.NamedExpr) else []) if isinstance(t, ast.Name)
             and answer_call(n.value)}
    out = []

    def visit(node: ast.AST, inside: bool) -> None:
        inside = inside or (isinstance(node, ast.With) and is_reading(node))
        if not inside:
            if isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "json":
                out.append(f"{node.lineno}: .json()")
            if (isinstance(node, ast.Subscript) and isinstance(node.ctx, ast.Load)
                    and isinstance(node.value, ast.Name) and node.value.id in bound):
                out.append(f"{node.lineno}: {node.value.id}[...]")
        for child in ast.iter_child_nodes(node):
            visit(child, inside)

    visit(fn, False)
    return out


@pytest.mark.parametrize("path", MODULES, ids=[p.stem for p in MODULES])
def test_every_answer_is_read_inside_reading(path):
    tree = ast.parse(path.read_text())
    found = [f"{fn.name} {x}" for fn in reached(tree, roots(path)) for x in outside(fn)]
    assert not found, f"{path.name} reads a system's answer outside `adapter.reading`: {found}"


@dataclasses.dataclass(frozen=True)
class Answers(harness.PageAdapter):
    """A system whose answer lacks its html. `careful` reads the answer inside `reading`, as an adapter
    must."""

    SUPPORTS: ClassVar[frozenset[str]] = frozenset({"html"})
    retries: ClassVar[int] = 0
    careful: bool = True

    def requests(self, wants):
        return [contract.Request(frozenset({"html"}), {})]

    def send(self, page, request, *, timeout):
        answer = {"wrong": "shape"}
        if self.careful:
            with core.reading("the answer's html"):
                return contract.Call({"html": answer["html"]})
        return contract.Call({"html": answer["html"]})

    def parse(self, raw, request):
        return {"html": raw["html"]}, {}


def test_a_malformed_answer_inside_reading_fails_the_page(tmp_path):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    rec = core.predict(Answers(), harness.Input(pdf, frozenset({"html"})))
    assert rec["output"] is None and "couldn't be read (the answer's html)" in rec["error"]["message"], rec


def test_a_bug_outside_reading_stops_the_run(tmp_path):
    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    with pytest.raises(KeyError):
        core.predict(Answers(careful=False), harness.Input(pdf, frozenset({"html"})))
