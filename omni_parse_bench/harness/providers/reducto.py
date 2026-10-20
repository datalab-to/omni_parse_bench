"""Reducto adapter: upload the page, POST /parse_async, poll /job/<id>.

The adapter is `Reducto`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
import html
import re
import time
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors, layout
from ..adapter import PageAdapter

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
class Reducto(PageAdapter):
    """The reducto adapter. Its fields are what reducto can be asked.

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

        opb run --system reducto --options '{"model": "legacy"}' --sample 20
    """

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

    name: ClassVar[str] = "reducto"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    keys: ClassVar[tuple[str, ...]] = ("REDUCTO_API_KEY",)
    workers: ClassVar[int] = 3

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Reducto) -> list[contract.Request]:
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
         config: Reducto | None = None) -> contract.Call:
    """Upload the page, submit the parse, poll until it is done, return the finished job."""
    config = config or Reducto()
    key = errors.key("REDUCTO_API_KEY", "reducto")
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    polls = 0
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        upload = {"file": (contract.upload_name(page), page.read_bytes(), media)}
        r = client.post(f"{base_url}/upload", files=upload, timeout=deadline.timeout(300))
        with adapter.reading("the uploaded file's id"):
            file_id = contract.json_object(r).get("file_id") if r.status_code == 200 else None
        if not file_id:
            raise errors.SystemFailed(f"upload HTTP {r.status_code}: {r.text}",
                                     status=r.status_code, body=r.text)
        r = client.post(f"{base_url}/parse_async", json={"input": file_id, **request.sent},
                        timeout=deadline.timeout(120))
        with adapter.reading("the job's id"):
            job_id = contract.json_object(r).get("job_id") if r.status_code == 200 else None
        if not job_id:
            raise errors.SystemFailed(f"parse_async HTTP {r.status_code}: {r.text}",
                                     status=r.status_code, body=r.text)
        retry = budget.PollRetry(deadline)
        with errors.job(job_id):
            while True:
                deadline.check(f"job {job_id} was still running after {polls} polls")
                try:
                    r = client.get(f"{base_url}/job/{job_id}", timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.transport(exc, "polling failed") from exc
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.SystemFailed(f"HTTP {r.status_code}: {r.text}",
                                             status=r.status_code, body=r.text)
                retry.reset()
                polls += 1
                with adapter.reading("the job's status"):
                    job = contract.json_object(r)
                if job.get("status") in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            cost = contract.Cost.in_credits(((job.get("result") or {}).get("usage") or {}).get("credits"),
                                            "usage.credits")
            if job.get("status") != "Completed":
                raise errors.SystemFailed(f"job {job.get('status')}: {str(job.get('reason'))}",
                                         status=200, body=job, cost=cost)
            result = (job.get("result") or {}).get("result") or {}
            # Note: a large result comes as a URL to it; it is fetched, so the saved answer holds it, with
            # the polls' retry, since failing here would re-run, and re-pay for, a job that is done.
            while result.get("type") == "url" and result.get("url"):
                try:
                    got = client.get(result.get("url"), timeout=deadline.timeout(300))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.transport(exc, "fetching the result failed", body=job, cost=cost) from exc
                if got.status_code == 200:
                    with adapter.reading("the result at its URL"):
                        job["result"]["result"] = got.json()
                    break
                if retry.again(got.status_code): continue
                # Note: the URL is presigned storage, not Reducto's API: its 403 (an expired link) says
                # nothing about the key, so the status is left out, or it would stop the run as an account
                # failure; a new call gets a new link.
                raise errors.SystemFailed(f"result URL HTTP {got.status_code}: {got.text}", status=None,
                                         body=job, cost=cost)
    return contract.Call(job, cost=cost, job_id=job_id)


def parse(raw: dict, request: contract.Request, config: Reducto | None = None) -> tuple[dict, dict]:
    """The outputs in a completed job: its content as html, and its blocks."""
    with adapter.reading("the job's chunks"):
        chunks = (((raw.get("result") or {}).get("result")) or {}).get("chunks")
        if chunks is None:
            raise errors.SystemFailed(f"completed with no chunks: {str(raw)}", status=200)
        blocks = [b for c in chunks for b in c.get("blocks") or []]
        md = "\n\n".join(described(c.get("content") or "", c.get("blocks") or []) for c in chunks)
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html": outputs[o] = markdown.to_html(md)
        if o == "blocks":
            try:
                with adapter.reading("the job's blocks"):
                    outputs[o] = layout_blocks(blocks)
            except errors.SystemFailed as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
