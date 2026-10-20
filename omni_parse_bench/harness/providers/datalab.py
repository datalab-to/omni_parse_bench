"""Datalab API adapter: POST /api/v1/convert, then poll for the result.

The adapter is `Datalab`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
import json
import re
import time
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from .. import budget, contract, errors, layout
from ..adapter import PageAdapter

DEFAULT_BASE_URL = "https://www.datalab.to"
SUPPORTS = frozenset({"html", "blocks"})
# Note: Datalab's own list (steps/core/document/block.py). Diagram and ChemicalBlock reach the API
# as Figure and Bibliography as ListGroup; ComplexRegion is mostly a drawing with labels in it.
LABELS = {
    "Text": "text", "SectionHeader": "heading", "ListGroup": "list", "Caption": "caption",
    "Footnote": "footnote", "PageHeader": "page_furniture", "PageFooter": "page_furniture",
    "Equation": "equation", "Code": "code", "TableOfContents": "text", "Bibliography": "text",
    "Table": "table", "Form": "form",
    "Picture": "figure", "Figure": "figure", "Diagram": "figure", "ChemicalBlock": "figure",
    "ComplexRegion": "figure",
}
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}


@dataclasses.dataclass(frozen=True)
class Datalab(PageAdapter):
    """The datalab adapter. Its fields are what datalab can be asked.

    `mode` selects the tier (`fast`, `balanced`, `accurate`). One call produces `html` and `blocks`
    together (`output_format=html,chunks`), with page headers and footers kept (the API's own switches
    `additional_config.keep_pageheader_in_output` and `keep_pagefooter_in_output`).

    Blocks come from the chunks output: each block's `block_type`, its `bbox` in the page's frame
    (`page_info`), and its text. Cost comes back in cents (`cost_breakdown`) and is converted once.

    Auth: DATALAB_API_KEY.

        opb run --system datalab --options '{"mode": "balanced"}' --sample 20
    """

    mode: str = dataclasses.field(
        default="accurate",
        metadata={"choices": ["fast", "balanced", "accurate"],
                  "help": "conversion tier; the published runs use balanced and accurate"})
    base_url: str = DEFAULT_BASE_URL
    poll_interval: float = 2.0

    name: ClassVar[str] = "datalab"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    keys: ClassVar[tuple[str, ...]] = ("DATALAB_API_KEY",)
    workers: ClassVar[int] = 10

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Datalab) -> list[contract.Request]:
    """One call for html and blocks, with headers kept."""
    if not wants: return []
    formats = ",".join(f for o, f in (("html", "html"), ("blocks", "chunks")) if o in wants)
    sent = {"mode": config.mode, "skip_cache": True, "disable_image_extraction": True,
            "disable_image_captions": True, "output_format": formats,
            "additional_config": {"keep_pageheader_in_output": True, "keep_pagefooter_in_output": True}}
    return [contract.Request(wants, sent)]


def _cost(body: dict) -> contract.Cost | None:
    """The cost this response states, or None if it does not say."""
    for source, value in (("cost_breakdown.final_cost_cents",
                           (body.get("cost_breakdown") or {}).get("final_cost_cents")),
                          ("total_cost", body.get("total_cost"))):
        found = contract.Cost.reported(value, source, cents=True)
        if found.usd is not None: return found
    return None


def blocks(chunks: dict) -> list[dict]:
    """The chunks output's blocks as the `blocks` output, in the frame of the first page."""
    info = chunks.get("page_info") or {}
    page = info.get("0") or info.get(0) or next(iter(info.values()), {})
    frame = (page.get("bbox") or [0, 0, 0, 0])[2:]
    if not all(frame):
        raise errors.SystemFailed(f"chunks carry no page frame: {str(info)}", status=200)
    return [layout.block(layout.label(LABELS, b.get("block_type") or ""), b["bbox"], frame,
                         re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.get("html") or "")).strip())
            for b in chunks.get("blocks") or [] if b.get("bbox") and str(b.get("page", 0)) == "0"]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Datalab | None = None) -> contract.Call:
    """POST the page, poll until it is done, return the finished conversion and its cost."""
    config = config or Datalab()
    key = errors.key("DATALAB_API_KEY", "datalab")
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    form = {k: json.dumps(v) if isinstance(v, dict) else str(v).lower() if isinstance(v, bool) else str(v)
            for k, v in request.sent.items()}
    polls = 0
    with httpx.Client(headers={"X-Api-Key": key}, timeout=120) as client:
        with page.open("rb") as fh:
            media = MEDIA.get(page.suffix.lower(), "application/pdf")
            resp = client.post(f"{base_url}/api/v1/convert", data=form,
                               files={"file": (contract.upload_name(page), fh, media)},
                               timeout=deadline.timeout(120))
        if resp.status_code != 200:
            raise errors.SystemFailed(f"HTTP {resp.status_code}: {resp.text}",
                                     status=resp.status_code, body=resp.text)
        with adapter.reading("the request's id"):
            request_id = contract.json_object(resp).get("request_id")
        if not request_id:
            raise errors.SystemFailed(f"no request_id in the response: {resp.text}",
                                     status=resp.status_code, body=resp.text)
        url = f"{base_url}/api/v1/convert/{request_id}"
        retry = budget.PollRetry(deadline)
        with errors.job(request_id):
            while True:
                deadline.check(f"request {request_id} was still running after {polls} polls")
                try:
                    r = client.get(url, timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.transport(exc, "polling failed") from exc
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.SystemFailed(f"HTTP {r.status_code}: {r.text}",
                                             status=r.status_code, body=r.text)
                retry.reset()
                polls += 1
                with adapter.reading("the conversion's status"):
                    body = contract.json_object(r)
                if body.get("status") == "complete":
                    if not body.get("success", True):
                        raise errors.SystemFailed(f"vendor reported failure: {str(body.get('error'))}",
                                                 status=200, body=body, cost=_cost(body))
                    return contract.Call(body, cost=_cost(body) or contract.Cost(), job_id=request_id)
                if body.get("status") in ("error", "failed", "expired"):
                    why = f"vendor reported {body.get('status')}: {str(body.get('error'))}"
                    raise errors.SystemFailed(why, status=200, body=body, cost=_cost(body))
                time.sleep(min(config.poll_interval, deadline.remaining()))


def parse(raw: dict, request: contract.Request, config: Datalab | None = None) -> tuple[dict, dict]:
    """The outputs in a completed conversion: its html, and its chunks as blocks."""
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html": outputs[o] = raw.get("html")
        if o == "blocks" and raw.get("chunks"):
            try:
                with adapter.reading("the chunks"):
                    outputs[o] = blocks(raw["chunks"])
            except errors.SystemFailed as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
