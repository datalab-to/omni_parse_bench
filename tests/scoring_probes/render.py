"""Run the scoring reference's cases, record them, and write their tables into the pages.

    python tests/scoring_probes/render.py --print   # run every case; print the record (observed.txt)
    python tests/scoring_probes/render.py --write   # run every case in a clean subprocess; write observed.txt
                                                    # and every generated block of docs/scoring/*.md

Each page holds generated blocks between `<!-- cases:ID -->` and `<!-- /cases -->`: a table of cases, or a
fixture (the html some cases share). `--write` refuses when a case no longer gives what it claims: change the
case (its mark, expectation and rule) and the prose around it first, then write.
"""
from __future__ import annotations

import importlib
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
DOCS = ROOT / "docs" / "scoring"
OBSERVED = HERE / "observed.txt"
# Each module of cases, and the page its blocks go in.
MODULES = {"readme": "README.md", "present_text": "present-text.md", "present_number": "present-number.md",
           "present_latex": "present-latex.md", "order": "order.md", "repeat": "repeat.md",
           "page_near_empty": "page_near_empty.md", "format_mark": "format.md",
           "table_cell": "table_cell.md", "layout_kind": "layout_kind.md", "internals": "internals.md"}
BLOCK = re.compile(r"(<!-- cases:([a-z0-9-]+) -->\n)(.*?)(<!-- /cases -->)", re.S)
TIMEOUT = 300


def load():
    """Every page's tables and fixtures: {page: ([Table], {name: html})}."""
    sys.path[:0] = [str(ROOT), str(HERE)]
    out = {}
    for name, page in MODULES.items():
        m = importlib.import_module(name)
        out[page] = (list(m.TABLES), dict(getattr(m, "FIXTURES", {})))
    labels = [c.label for tables, _ in out.values() for t in tables for c in t.cases]
    dup = sorted({x for x in labels if labels.count(x) > 1})
    assert not dup, f"duplicate labels: {dup}"
    return out


def run_all() -> str:
    """The record: per table, one line per case: label, result and (for a failure) why, separated by tabs."""
    lines = []
    for tables, _ in load().values():
        for t in tables:
            lines.append(f"## {t.id}")
            for c in t.cases:
                result, detail = c.run()
                fields = [c.label, result, detail] if detail else [c.label, result]
                lines.append("\t".join(fields).replace("\n", "\\n"))
    return "\n".join(lines) + "\n"


def parse(record: str) -> dict[str, dict[str, tuple[str, str]]]:
    """A record as {table: {label: (result, detail)}}."""
    out: dict[str, dict[str, tuple[str, str]]] = {}
    for line in record.splitlines():
        if line.startswith("## "):
            current = out.setdefault(line[3:], {})
        elif line:
            label, result, *detail = line.split("\t", 2)
            current[label] = (result, detail[0] if detail else "")
    return out


def broken(pages, record) -> list[str]:
    """Each case whose recorded result is not what it claims."""
    got = parse(record)
    out = []
    for page, (tables, _) in pages.items():
        for t in tables:
            for c in t.cases:
                r = got.get(t.id, {}).get(c.label)
                if r is None or r[0] != c.expect:
                    out.append(f"{page} `{c.label}` ({c.rule}): claims {c.expect!r}, gives "
                               f"{r[0] if r else 'nothing'!r}{' (' + r[1] + ')' if r and r[1] else ''}")
    return out


def blocks(pages, record) -> dict[str, dict[str, str]]:
    """Each page's generated blocks, from the cases and a record: {page: {id: markdown}}."""
    from cases import render
    got = parse(record)
    out = {}
    for page, (tables, fixtures) in pages.items():
        out[page] = {t.id: render(t, got.get(t.id, {})) for t in tables}
        out[page] |= {name: f"```html\n{h}\n```\n" for name, h in fixtures.items()}
    return out


def rewrite(text: str, made: dict[str, str]) -> tuple[str, list[str]]:
    """`text` with each generated block replaced, and the ids of blocks it lacks or does not know."""
    seen = []

    def one(m: re.Match[str]) -> str:
        seen.append(m[2])
        return m[1] + made[m[2]] + m[4] if m[2] in made else m[0]
    new = BLOCK.sub(one, text)
    return new, sorted(set(made) ^ set(seen))


def record_in_subprocess() -> tuple[str, str, int]:
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([str(ROOT), str(HERE)]), "PYTHONHASHSEED": "0",
           "PYTHONIOENCODING": "utf-8", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONWARNINGS": "ignore"}
    r = subprocess.run([sys.executable, str(HERE / "render.py"), "--print"], cwd=ROOT, env=env,
                       capture_output=True, text=True, encoding="utf-8", check=False, timeout=TIMEOUT)
    return r.stdout, r.stderr, r.returncode


def write() -> int:
    record, err, code = record_in_subprocess()
    if code or err.strip():
        print(f"Not writing: the cases exited {code} or wrote to stderr:\n{err[-2000:]}")
        return 1
    pages = load()
    if bad := broken(pages, record):
        print("Not writing: these cases no longer give what they claim. Update each case (mark, expectation,"
              " rule) and the prose that cites it, then write again:\n  " + "\n  ".join(bad))
        return 1
    OBSERVED.write_text(record, encoding="utf-8")
    for page, made in blocks(pages, record).items():
        path = DOCS / page
        new, odd = rewrite(path.read_text(encoding="utf-8"), made)
        if odd:
            print(f"{page}: blocks missing or unknown: {odd}")
            return 1
        path.write_text(new, encoding="utf-8")
    print(f"wrote {OBSERVED.relative_to(ROOT)} and the tables of {len(pages)} pages")
    return 0


if __name__ == "__main__":
    if sys.argv[1:] == ["--print"]:
        sys.stdout.write(run_all())
    elif sys.argv[1:] == ["--write"]:
        sys.exit(write())
    else:
        print(__doc__)
        sys.exit(2)
