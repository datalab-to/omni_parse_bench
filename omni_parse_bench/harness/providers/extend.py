"""Extend adapter: upload the page, POST /parse_runs, poll /parse_runs/<id>.

One call produces both outputs. Extend returns the page as a chunk whose content is its typed
blocks joined (text, heading, section_heading, header, footer, page_number, table, figure,
key_value, formula, barcode, ...), each block with a box in the page's pixels. So:

- `html` is Extend's page content, as it returns it; and
- `blocks` are the blocks, their text with tags removed as for every vendor.

Figures: Extend writes a generated description of each figure as a `<caption>` inside its
`<figure>` (on 10 figure pages every one was a description, none a printed caption), and has no
switch to turn only that off. No vendor is sent free-text instructions, so it is translated, not
dropped: each such caption becomes an image's alt text in its place, where every vendor's image
descriptions are, and the scorer treats it as it treats theirs.
Tables are asked for as html. Extend's agentic passes are on, as Reducto's are: a vision model
corrects low-confidence OCR and handwriting (`blockOptions.text.agentic`) and table structure
(`blockOptions.tables.agentic`), each off by default and billed where it triggers; an image page
is converted to PDF at `imageConversionQuality` high (default medium). Cost comes back in Extend
credits (`usage.credits`). A run that fails with an outage code (`OUTAGES`) is retried as a 5xx is.

Auth: EXTEND_API_KEY, and EXTEND_WORKSPACE_ID when the key spans several workspaces.

    opb predict --provider extend --page page.pdf --options '{"engine": "parse_light"}'
"""
from __future__ import annotations

import dataclasses
import html
import os
import re
import time
from pathlib import Path

import httpx

from ... import markdown
from .. import budget, contract, errors, layout

DEFAULT_BASE_URL = "https://api.extend.ai"
API_VERSION = "2026-02-09"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
# Note: Extend's documented block types. table_head and table_cell come only with cellBlocksEnabled.
LABELS = {
    "text": "text", "heading": "heading", "section_heading": "heading", "header": "page_furniture",
    "footer": "page_furniture", "page_number": "page_furniture", "formula": "equation", "legend": "caption",
    "table": "table", "table_head": "table", "table_cell": "table",
    "key_value": "form", "figure": "figure", "barcode": "figure",
}
# Note: Extend's run statuses, upper-cased: PROCESSED or COMPLETED is a finished run, the rest a failed one.
SUCCEEDED = frozenset({"PROCESSED", "COMPLETED"})
TERMINAL = SUCCEEDED | {"FAILED", "CANCELLED", "ERROR"}
# Note: Extend's failureReason codes for its own fault, not the file's; recorded as a 500, so they are
# retried as any vendor's internal error is.
OUTAGES = frozenset({"INTERNAL_ERROR", "OCR_ERROR"})


@dataclasses.dataclass(frozen=True)
class Config:
    """What extend can be asked."""

    engine: str = dataclasses.field(
        default="parse_performance",
        metadata={"choices": ["parse_performance", "parse_light", "parse_auto"],
                  "help": "parse_performance is Extend's most accurate engine"})
    formulas: bool = dataclasses.field(
        default=True, metadata={"help": "formula detection and parsing (blockOptions.formulas.enabled)"})
    agentic_text: bool = dataclasses.field(
        default=True, metadata={"help": "a vision model corrects low-confidence OCR and handwriting "
                                        "(blockOptions.text.agentic.enabled)"})
    agentic_tables: bool = dataclasses.field(
        default=True, metadata={"help": "a vision model corrects table structure "
                                        "(blockOptions.tables.agentic.enabled)"})
    image_quality: str = dataclasses.field(
        default="high", metadata={"choices": ["high", "medium", "low"],
                                  "help": "quality of an image's conversion to PDF "
                                          "(advancedOptions.imageConversionQuality)"})
    api_version: str = API_VERSION
    base_url: str = DEFAULT_BASE_URL
    poll_interval: float = 3.0


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call for every output."""
    blocks = {"text": {"agentic": {"enabled": config.agentic_text}},
              "tables": {"targetFormat": "html", "agentic": {"enabled": config.agentic_tables}},
              "formulas": {"enabled": config.formulas}}
    sent = {"config": {"target": "markdown", "chunkingStrategy": {"type": "page"}, "engine": config.engine,
                       "blockOptions": blocks,
                       "advancedOptions": {"imageConversionQuality": config.image_quality}}}
    return [contract.Request(wants & SUPPORTS, sent)]


_FIGURE = re.compile(r"<figure\b.*?</figure>", re.S | re.I)
_CAPTION = re.compile(r"<caption>(.*?)</caption>", re.S | re.I)
_OWN_TAG = re.compile(r"</?[a-z]+_[a-z_]+\b[^<>]*>", re.I)


def described(md: str) -> str:
    """`md` with each <caption> inside a <figure> as an image whose alt text it is, on one line, so
    the description's line breaks and list lines can't turn it into page text."""
    alt = lambda m: f'<img alt="{html.escape(" ".join(m[1].split()), quote=True)}">'  # noqa: E731
    return _FIGURE.sub(lambda f: _CAPTION.sub(alt, f[0]), md)


def translated(md: str) -> str:
    """Extend's markup as HTML: figure descriptions as alt text (`described`), and its own tags
    (`<page_number>`), whose underscore no HTML tag name has, unwrapped to their text, which a
    renderer would otherwise print as literal tags."""
    return _OWN_TAG.sub("", described(md))


def layout_blocks(blocks: list[dict], turned: int = 0) -> list[dict]:
    """The blocks as the `blocks` output, their boxes divided by the page's size in the same pixels.

    `turned` is the clockwise rotation Extend applied to make the page upright (its page metadata's
    `rotationApplied`): its boxes are in that upright frame, so they are turned back to the page's.
    """
    out = []
    for b in blocks:
        box, page = b.get("boundingBox"), (b.get("metadata") or {}).get("page") or {}
        # Note: each of a box's sides is nullable in Extend's schema; a box without one is no place.
        if not box or None in (box.get(k) for k in ("left", "top", "right", "bottom")): continue
        if page.get("number", 1) != 1: continue
        if not (page.get("width") and page.get("height")):
            raise errors.VendorError(f"block carries no page size: {str(b.get('metadata'))[:200]}",
                                     status=200)
        corners = (box["left"], box["top"], box["right"], box["bottom"])
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.get("content") or "")).strip()
        out.append(layout.block(layout.label(LABELS, b.get("type") or ""), corners,
                                (page["width"], page["height"]), plain))
    if turned % 360: out = [x | {"bbox": unturned(x["bbox"], turned)} for x in out]
    return out


def unturned(box: list[float], turned: int) -> list[float]:
    """A box `[x0, y0, x1, y1]` (fractions) in a frame turned `turned` degrees clockwise, in the frame
    before."""
    if turned % 90: raise errors.VendorError(f"rotationApplied {turned} isn't a quarter turn", status=200)
    x0, y0, x1, y1 = box
    # Note: undoing one clockwise quarter turn sends the upright point (u, v) to (v, 1 - u) on the page.
    for _ in range(turned // 90 % 4): x0, y0, x1, y1 = y0, 1 - x1, y1, 1 - x0
    return [x0, y0, x1, y1]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Config | None = None) -> contract.Call:
    """Upload the page, start the parse run, poll until it is done, return the finished run."""
    config = config or Config()
    key = os.environ.get("EXTEND_API_KEY")
    if not key:
        raise errors.MissingCredential("EXTEND_API_KEY is not set")
    headers = {"Authorization": f"Bearer {key}", "x-extend-api-version": config.api_version}
    if workspace := os.environ.get("EXTEND_WORKSPACE_ID"): headers["x-extend-workspace-id"] = workspace
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    polls = 0
    with httpx.Client(headers=headers, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        upload = {"file": (contract.upload_name(page), page.read_bytes(), media)}
        r = client.post(f"{base_url}/files/upload", files=upload, timeout=deadline.timeout(300))
        if r.status_code != 200 or not (file_id := r.json().get("id")):
            raise errors.VendorError(f"upload HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        r = client.post(f"{base_url}/parse_runs", json={"file": {"id": file_id}, **request.sent},
                        timeout=deadline.timeout(120))
        if r.status_code != 200 or not (run_id := r.json().get("id")):
            raise errors.VendorError(f"parse_runs HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        retry = budget.PollRetry(deadline)
        with errors.job(run_id):
            while True:
                deadline.check(f"parse run {run_id} was still running after {polls} polls")
                try:
                    r = client.get(f"{base_url}/parse_runs/{run_id}", timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.VendorError(f"polling failed: {exc}"[:300], status=None) from None
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.VendorError(f"HTTP {r.status_code}: {r.text[:300]}",
                                             status=r.status_code, body=r.text)
                retry.ok()
                polls += 1
                run = r.json()
                if str(run.get("status", "")).upper() in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            cost = contract.Cost.in_credits((run.get("usage") or {}).get("credits"), "usage.credits")
            if (status := str(run.get("status", "")).upper()) not in SUCCEEDED:
                # Note: status 200, so neither `predict` nor --retry-failed asks again: the vendor answered,
                # unless the reason is an outage of Extend's, which a 500 retries.
                why = f"{run.get('failureReason')}: {run.get('failureMessage')}"
                outage = run.get("failureReason") in OUTAGES
                raise errors.VendorError(f"parse run {status}: {why[:300]}", status=500 if outage else 200,
                                         raw=run, cost=cost)
    return contract.Call(run, cost=cost, job_id=run_id)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The outputs in a processed run: its content as html, and its blocks."""
    chunks = (raw.get("output") or {}).get("chunks")
    if chunks is None:
        raise errors.VendorError(f"processed with no chunks: {str(raw)[:300]}", status=200)
    blocks = [b for c in chunks for b in c.get("blocks") or []]
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html":
            outputs[o] = markdown.to_html(translated("\n\n".join(c.get("content") or "" for c in chunks)))
        if o == "blocks":
            pages = ((raw.get("output") or {}).get("metadata") or {}).get("pages") or []
            turned = next((x.get("rotationApplied") or 0 for x in pages if x.get("number", 1) == 1), 0)
            try: outputs[o] = layout_blocks(blocks, turned)
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = f"blocks: {type(exc).__name__}: {exc}"
    return outputs, errs
