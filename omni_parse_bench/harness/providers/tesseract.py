"""Tesseract: plain OCR with no model of the page beyond its characters, the benchmark's floor.

A PDF page is rendered at `render_dpi` (pypdfium2); an image is read as it is. Tesseract first
detects the page's script itself (`--psm 0`) and then reads it with that script's model, English
when it detects none: it is told nothing about the page, as a tool with no metadata would be. Its
answer is plain text, written as html inside <pre>, escaped, and nothing else is done to it.

No layout blocks. It runs locally, costs
nothing and needs no key, only the `tesseract` binary with its script models:

    brew install tesseract tesseract-lang     # or: apt install tesseract-ocr tesseract-ocr-script-*

    opb predict --provider tesseract --page page.pdf
"""
from __future__ import annotations

import dataclasses
import functools
import html as _html
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from .. import budget, contract, errors, raster

SUPPORTS = frozenset({"html"})
# Tesseract's script names, as its detection prints them, to its script models.
SCRIPTS = {s: f"script/{s}" for s in (
    "Latin", "Cyrillic", "Greek", "Arabic", "Thai", "Hebrew", "Ethiopic", "Armenian", "Bengali", "Devanagari",
    "Kannada", "Georgian", "Khmer", "Hangul", "Lao", "Malayalam", "Myanmar", "Gurmukhi", "Gujarati", "Oriya",
    "Tamil", "Telugu", "Sinhala", "Tibetan", "Thaana", "Syriac", "Fraktur", "Vietnamese", "Japanese")}
SCRIPTS |= {"Han": "script/HanS+script/HanT", "HanS": "script/HanS", "HanT": "script/HanT",
            "Katakana": "script/Japanese", "Hiragana": "script/Japanese", "Korean": "script/Hangul"}
FALLBACK = "eng"
_SCRIPT = re.compile(r"Script: (\w+)")


@dataclasses.dataclass(frozen=True)
class Config:
    """What tesseract can be asked."""

    render_dpi: int = dataclasses.field(default=300,
                                        metadata={"help": "a PDF page is rendered at this resolution"})
    model: str = dataclasses.field(default="auto", metadata={
        "help": "auto detects the page's script and uses its model; or a Tesseract model, e.g. eng"})


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call, for html."""
    return [contract.Request(wants & SUPPORTS, {"render_dpi": config.render_dpi, "model": config.model})]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Config | None = None) -> contract.Call:
    """Read the page; the answer is its text, the script detected and the model used."""
    config = config or Config()
    if not shutil.which("tesseract"):
        raise errors.MissingDependency("tesseract isn't installed: brew install tesseract tesseract-lang")
    deadline = budget.Budget(timeout)
    with tempfile.TemporaryDirectory() as tmp:
        image = page
        if page.suffix.lower() == ".pdf":
            image = Path(tmp) / "page.png"
            raster.render(page, lambda _: config.render_dpi / 72).save(image)
        script, model = None, config.model
        if model == "auto":
            script = detect(image, deadline)
            model = SCRIPTS.get(script, FALLBACK)
        text = run(["tesseract", str(image), "-", "-l", model], deadline).stdout
    return contract.Call({"text": text, "script": script, "model": model, "version": version()})


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The text as html: escaped, inside <pre>."""
    h = "<pre>" + _html.escape(raw["text"]) + "</pre>"
    return {o: h for o in request.outputs}, {}


def detect(image: Path, deadline: budget.Budget) -> str | None:
    """The script Tesseract detects on the image, or None when it can't tell."""
    osd = run(["tesseract", str(image), "-", "--psm", "0"], deadline, check=False)
    return m[1] if (m := _SCRIPT.search(osd.stdout + osd.stderr)) else None


def run(cmd: list[str], deadline: budget.Budget, check: bool = True) -> subprocess.CompletedProcess:
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=max(1.0, deadline.remaining()))
    except subprocess.TimeoutExpired:
        raise errors.VendorTimeout(f"tesseract ran past the call's {deadline.total:.0f} s") from None
    if check and out.returncode != 0:
        raise errors.VendorError(f"tesseract exited {out.returncode}: {out.stderr[:300]}", status=None)
    return out


@functools.cache
def version() -> str:
    """Tesseract's version line, recorded with each answer."""
    out = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=60).stdout
    return out.split("\n")[0].strip()
