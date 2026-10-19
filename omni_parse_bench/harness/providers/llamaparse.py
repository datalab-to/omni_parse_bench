"""LlamaParse adapter (v2 API): upload the page with its configuration, poll, read the result.

The adapter is `LlamaParse`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
import json
import os
import re
import time
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors, layout
from ..adapter import PageAdapter

DEFAULT_BASE_URL = "https://api.cloud.llamaindex.ai"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
ITEM_LABELS = {
    "text": "text", "heading": "heading", "header": "page_furniture", "footer": "page_furniture",
    "code": "code", "list": "list", "link": "text", "table": "table", "image": "figure",
}
# Note: box labels are free strings
BOX_LABELS = {
    "text": "text", "paragraph_title": "heading", "doc_title": "heading", "list": "list",
    "caption": "caption", "formula": "equation", "header": "page_furniture", "footer": "page_furniture",
    "key-value-region": "form", "code": "code", "footnote": "footnote", "reference": "text", "form": "form",
    "checkbox-selected": "form", "checkbox-unselected": "form",
    "table": "table", "image": "figure", "chart": "figure", "seal": "figure",
}
TERMINAL = frozenset({"COMPLETED", "FAILED", "CANCELLED"})


@dataclasses.dataclass(frozen=True)
class LlamaParse(PageAdapter):
    """The llamaparse adapter. Its fields are what llamaparse can be asked.

    One call produces both outputs:

    - `html` is LlamaParse's page `header`, its page markdown and its page `footer`, in that order.
      The markdown leaves out what LlamaParse typed page header and footer, and returns them beside it
      in those fields of the same page, so they go back where a header and a footer sit; and
    - `blocks` are its items' boxes. An item (text, heading, table, image, header, footer, ...) can
      have several boxes, each with a finer layout label (form, paragraph_title, table, image, ...)
      and the span of the item's text it covers. A box's label is looked up in `BOX_LABELS`; a box
      with no label takes its item's type from `ITEM_LABELS`. Items nest (a list's items, the lines of
      a header), each level with its own boxes, and every level is read.

    Tables are asked for as html. The tier is `agentic_plus`, LlamaParse's most accurate. Cost comes
    back in LlamaParse credits (`job.usage.credits`).

    Auth: LLAMA_CLOUD_API_KEY.

        opb run --providers llamaparse --options '{"llamaparse": {"tier": "agentic"}}' --sample 20
    """

    tier: str = dataclasses.field(
        default="agentic_plus",
        metadata={"choices": ["fast", "cost_effective", "agentic", "agentic_plus"],
                  "help": "agentic_plus is LlamaParse's most accurate tier"})
    version: str = dataclasses.field(default="latest", metadata={"help": "the tier's dated version"})
    base_url: str = DEFAULT_BASE_URL
    poll_interval: float = 3.0

    name: ClassVar[str] = "llamaparse"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = 3

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: LlamaParse) -> list[contract.Request]:
    """One call for every output; html puts back the headers and footers the page markdown leaves out."""
    # Note: without disable_cache LlamaParse returns an earlier job for a file it has seen, so a rerun
    # measures neither this parse nor its time; the other vendors parse every page afresh.
    sent = {"tier": config.tier, "version": config.version, "disable_cache": True,
            "output_options": {"markdown": {"tables": {"output_tables_as_markdown": False}}}}
    if "html" in wants:
        sent["derived"] = {"html": "the page's header, markdown and footer fields joined"}
    return [contract.Request(wants & SUPPORTS, sent)]


def layout_blocks(page: dict) -> list[dict]:
    """The page's item boxes as the `blocks` output, in the frame of the page's size."""
    frame = (page.get("page_width"), page.get("page_height"))
    if not all(frame):
        raise errors.VendorError(f"items carry no page size: {str(page)[:200]}", status=200)
    out = []
    for item in items(page.get("items")):
        md = item.get("md") or item.get("value") or ""
        for box in item.get("bbox") or []:
            if not all(isinstance(box.get(k), (int, float)) for k in "xywh"): continue
            kind = layout.label(BOX_LABELS, box["label"]) if box.get("label") else \
                layout.label(ITEM_LABELS, item.get("type") or "")
            # Note: end_index is inclusive: a box over a whole item ends at len(md) - 1.
            span = md[box["start_index"]:box["end_index"] + 1] if box.get("end_index") is not None else md
            plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", span)).strip()
            corners = (box["x"], box["y"], box["x"] + box["w"], box["y"] + box["h"])
            out.append(layout.block(kind, corners, frame, plain))
    return out


def items(xs: list[dict] | None) -> list[dict]:
    """Every item of a page's tree, each before the items nested in it."""
    return [y for x in xs or [] for y in (x, *items(x.get("items")))]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: LlamaParse | None = None) -> contract.Call:
    """Upload the page with its configuration, poll until it is done, return the result and cost."""
    config = config or LlamaParse()
    key = os.environ.get("LLAMA_CLOUD_API_KEY")
    if not key:
        raise errors.MissingCredential("LLAMA_CLOUD_API_KEY is not set")
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    configuration = {k: v for k, v in request.sent.items() if k != "derived"}
    polls = 0
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        r = client.post(f"{base_url}/api/v2/parse/upload", data={"configuration": json.dumps(configuration)},
                        files={"file": (contract.upload_name(page), page.read_bytes(), media)},
                        timeout=deadline.timeout(300))
        with adapter.reading("the job's id"):
            job_id = contract.json_object(r).get("id") if r.status_code == 200 else None
        if not job_id:
            raise errors.VendorError(f"upload HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        retry = budget.PollRetry(deadline)
        with errors.job(job_id):
            while True:
                deadline.check(f"job {job_id} was still running after {polls} polls")
                try:
                    r = client.get(f"{base_url}/api/v2/parse/{job_id}", timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.VendorError(f"polling failed: {exc}"[:300], status=None) from None
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.VendorError(f"HTTP {r.status_code}: {r.text[:300]}",
                                             status=r.status_code, body=r.text)
                retry.reset()
                polls += 1
                with adapter.reading("the job's status"):
                    got = contract.json_object(r)
                    job = got.get("job") or got
                    if not isinstance(job, dict): raise ValueError(f"the job is a JSON {type(job).__name__}")
                if job.get("status") in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            if job.get("status") != "COMPLETED":
                raise errors.VendorError(f"job {job.get('status')}: {str(job.get('error_message'))[:300]}",
                                         status=200, raw={"job": job}, cost=_cost({"job": job}, job))
            # Note: the result is fetched with the same retry as the polls, since failing here would
            # re-run, and re-pay for, a job that is done.
            while True:
                try:
                    r = client.get(f"{base_url}/api/v2/parse/{job_id}",
                                   params={"expand": "markdown,items,usage"}, timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    why = f"fetching the result failed: {exc}"[:300]
                    raise errors.VendorError(why, status=None) from None
                if r.status_code == 200: break
                if retry.again(r.status_code): continue
                raise errors.VendorError(f"result HTTP {r.status_code}: {r.text[:300]}",
                                         status=r.status_code, body=r.text)
    with adapter.reading("the job's result"):
        body = contract.json_object(r)
    # Note: the last poll's job is kept beside the result: usage can be set on one and null on the other.
    body["poll_job"] = job
    return contract.Call(body, cost=_cost(body, job), job_id=job_id)


def _cost(body: dict, job: dict) -> contract.Cost:
    """The credits the result or the last poll states; usage can be null on one and set on the other."""
    credits = next((c for j in (body.get("job") or {}, job) if (c := (j.get("usage") or {}).get("credits"))
                    is not None), None)
    return contract.Cost.in_credits(credits, "job.usage.credits")


def parse(raw: dict, request: contract.Request, config: LlamaParse | None = None) -> tuple[dict, dict]:
    """The outputs in a result: header, markdown and footer as html, and blocks."""
    pages = [p for p in (raw.get("markdown") or {}).get("pages") or [] if p.get("page_number", 1) == 1]
    items = [p for p in (raw.get("items") or {}).get("pages") or [] if p.get("page_number", 1) == 1]
    if not pages:
        raise errors.VendorError(f"completed with no markdown: {str(raw)[:300]}", status=200)
    # Note: a job completes although a page of it failed; that page carries success false and its error.
    if pages[0].get("success") is False:
        raise errors.VendorError(f"the page failed: {str(pages[0].get('error'))[:300]}", status=200)
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html":
            parts = (pages[0].get("header"), pages[0].get("markdown"), pages[0].get("footer"))
            outputs[o] = markdown.to_html("\n\n".join(x for x in parts if x))
        if o == "blocks" and items:
            try: outputs[o] = layout_blocks(items[0])
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
