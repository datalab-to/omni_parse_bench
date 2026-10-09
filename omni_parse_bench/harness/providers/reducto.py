"""Reducto adapter: upload the page, POST /parse_async, poll /job/<id>.

One call produces both outputs. Reducto returns the page as typed blocks (Header, Footer,
Page Number, Title, Section Header, Text, Table, Figure, Key Value, ...), each with a normalized
box and its content, markdown with tables as html. So:

- `html` is Reducto's own page content, with r-1's figure descriptions as alt text (below); and
- `blocks` are the blocks, their text with tags removed as for every vendor.

Nothing else is changed: markers such as `<empty>` and `<signature>` are left for the scorer, which
reads them as tags, as it does for every vendor. Tables are asked for as html.

The model is r-1, Reducto's newest (`settings.model`; a request without one runs the legacy
pipeline). r-1 writes each figure as a description of it (with a `<verbose>` list of a chart's
words), in the page content as if printed, and has no switch for it; as with Extend's figure
captions, each becomes an image's alt text in its place (`described`), where every vendor's image
descriptions are, and the scorer treats it as it treats theirs. r-1 does what the legacy agentic
passes did itself, and its docs say to leave them out, so they and `extraction_mode` are sent only
with `model` legacy. There, agentic enrichment runs on tables (`max`) and on text (OCR correction by
a vision model), not on figures, where it turns a chart into a data table, which isn't page text,
and figures aren't summarized, since a summary is text the page doesn't print (Datalab's
`disable_image_captions`). Cost comes back in Reducto credits (`usage.credits`).

Auth: REDUCTO_API_KEY.

    opb predict --provider reducto --page page.pdf --options '{"model": "legacy"}'
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

DEFAULT_BASE_URL = "https://platform.reducto.ai"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
# Note: Reducto's documented list (ParseBlock.type). Key Value is a form region, as Datalab's Form.
LABELS = {
    "Text": "text", "Title": "heading", "Section Header": "heading", "List Item": "list",
    "Header": "page_furniture", "Footer": "page_furniture", "Page Number": "page_furniture",
    "Comment": "text",
    "Table": "table", "Figure": "figure", "Key Value": "form", "Signature": "figure",
}
TERMINAL = frozenset({"Completed", "Failed", "Error", "Cancelled"})


@dataclasses.dataclass(frozen=True)
class Config:
    """What reducto can be asked."""

    model: str = dataclasses.field(
        default="r-1", metadata={"choices": ["r-1", "legacy"],
                                 "help": "r-1 is Reducto's newest; the rest of the options apply to legacy"})
    agentic_table_mode: str = dataclasses.field(
        default="max",
        metadata={"choices": ["off", "default", "max"],
                  "help": "agentic table enrichment; max enriches every table, off sends none"})
    agentic_text: bool = dataclasses.field(
        default=True, metadata={"help": "agentic OCR correction of text by a vision model"})
    extraction_mode: str = dataclasses.field(
        default="hybrid", metadata={"choices": ["hybrid", "ocr"],
                                    "help": "hybrid adds the PDF's embedded text to OCR; ocr reads pixels"})
    base_url: str = DEFAULT_BASE_URL
    poll_interval: float = 3.0


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call for every output."""
    if config.model == "r-1":
        settings, enhance = {"model": "r-1"}, {}
    else:
        enhance = {"summarize_figures": False}
        table = {"scope": "table", "mode": config.agentic_table_mode}
        agentic = [] if config.agentic_table_mode == "off" else [table]
        if config.agentic_text: agentic.append({"scope": "text"})
        if agentic: enhance["agentic"] = agentic
        settings = {"model": "legacy", "extraction_mode": config.extraction_mode}
    sent = {"settings": settings, **({"enhance": enhance} if enhance else {}),
            "formatting": {"table_output_format": "html"},
            "retrieval": {"chunking": {"chunk_mode": "disabled"}}}
    return [contract.Request(wants & SUPPORTS, sent)]


def described(content: str, blocks: list[dict]) -> str:
    """A chunk's `content` with each figure r-1 described as an image whose alt text the description
    is, on one line. A legacy figure's content is the words printed in it, page text, and is kept."""
    for b in blocks:
        if b.get("type") != "Figure" or (b.get("extra") or {}).get("model") != "r-1": continue
        if said := b.get("content"):
            alt = html.escape(" ".join(said.split()), quote=True)
            content = content.replace(said, f'<img alt="{alt}">', 1)
    return content


def layout_blocks(blocks: list[dict]) -> list[dict]:
    """The blocks as the `blocks` output; Reducto's boxes are already fractions of the page."""
    out = []
    for b in blocks:
        box = b.get("bbox") or {}
        if not box or box.get("page", 1) != 1: continue
        x0, y0 = box["left"], box["top"]
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.get("content") or "")).strip()
        corners = (x0, y0, x0 + box["width"], y0 + box["height"])
        out.append(layout.block(layout.label(LABELS, b.get("type") or ""), corners, (1.0, 1.0), plain))
    return out


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Config | None = None) -> contract.Call:
    """Upload the page, submit the parse, poll until it is done, return the finished job."""
    config = config or Config()
    key = os.environ.get("REDUCTO_API_KEY")
    if not key:
        raise errors.MissingCredential("REDUCTO_API_KEY is not set")
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    polls = 0
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        upload = {"file": (contract.upload_name(page), page.read_bytes(), media)}
        r = client.post(f"{base_url}/upload", files=upload, timeout=deadline.timeout(300))
        if r.status_code != 200 or not (file_id := r.json().get("file_id")):
            raise errors.VendorError(f"upload HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        r = client.post(f"{base_url}/parse_async", json={"input": file_id, **request.sent},
                        timeout=deadline.timeout(120))
        if r.status_code != 200 or not (job_id := r.json().get("job_id")):
            raise errors.VendorError(f"parse_async HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        retry = budget.PollRetry(deadline)
        with errors.job(job_id):
            while True:
                deadline.check(f"job {job_id} was still running after {polls} polls")
                try:
                    r = client.get(f"{base_url}/job/{job_id}", timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.VendorError(f"polling failed: {exc}"[:300], status=None) from None
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.VendorError(f"HTTP {r.status_code}: {r.text[:300]}",
                                             status=r.status_code, body=r.text)
                retry.ok()
                polls += 1
                job = r.json()
                if job.get("status") in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            cost = contract.Cost.in_credits(((job.get("result") or {}).get("usage") or {}).get("credits"),
                                            "usage.credits")
            if job["status"] != "Completed":
                raise errors.VendorError(f"job {job['status']}: {str(job.get('reason'))[:300]}", status=200,
                                         raw=job, cost=cost)
            result = (job.get("result") or {}).get("result") or {}
            # Note: a large result comes as a URL to it; it is fetched, so the saved answer holds it, with
            # the polls' retry, since failing here would re-run, and re-pay for, a job that is done.
            while result.get("type") == "url" and result.get("url"):
                try:
                    got = client.get(result["url"], timeout=deadline.timeout(300))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.VendorError(f"fetching the result failed: {exc}"[:300], status=None,
                                             raw=job, cost=cost) from None
                if got.status_code == 200:
                    job["result"]["result"] = got.json()
                    break
                if retry.again(got.status_code): continue
                # Note: the URL is presigned storage, not Reducto's API: its 403 (an expired link) says
                # nothing about the key, so the status is left out, or it would stop the run as an account
                # failure; a new call gets a new link.
                raise errors.VendorError(f"result URL HTTP {got.status_code}: {got.text[:200]}", status=None,
                                         raw=job, cost=cost)
    return contract.Call(job, cost=cost, job_id=job_id)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The outputs in a completed job: its content as html, and its blocks."""
    chunks = (((raw.get("result") or {}).get("result")) or {}).get("chunks")
    if chunks is None:
        raise errors.VendorError(f"completed with no chunks: {str(raw)[:300]}", status=200)
    blocks = [b for c in chunks for b in c.get("blocks") or []]
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html":
            pages = (described(c.get("content") or "", c.get("blocks") or []) for c in chunks)
            outputs[o] = markdown.to_html("\n\n".join(pages))
        if o == "blocks":
            try: outputs[o] = layout_blocks(blocks)
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = f"blocks: {type(exc).__name__}: {exc}"
    return outputs, errs
