"""Azure Content Understanding adapter: the prebuilt layout analyzer, POST :analyzeBinary, poll.

The adapter is `Azure`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import dataclasses
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

API_VERSION = "2025-11-01"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
PAGE_MARKER = re.compile(r'<!--\s*Page(?:Header|Footer|Number)\s*[:=]\s*"?(.*?)"?\s*-->', re.S)
SOURCE = re.compile(r"D\((\d+),([^)]*)\)")
# Note: Azure's documented paragraph roles; a paragraph with no role is body text.
LABELS = {
    "": "text", "title": "heading", "sectionHeading": "heading", "pageHeader": "page_furniture",
    "pageFooter": "page_furniture", "pageNumber": "page_furniture", "footnote": "footnote",
    "formulaBlock": "equation",
    "table": "table", "figure": "figure",
}
TERMINAL = frozenset({"succeeded", "failed", "canceled", "cancelled"})


@dataclasses.dataclass(frozen=True)
class Azure(PageAdapter):
    """The azure adapter. Its fields are what azure can be asked.

    `endpoint` has no default to give, since every Azure resource has its own; it is empty here, so
    a `Azure` can be built (`opb providers`, a run's name), and `call` refuses it.

    One call produces both outputs. Azure returns the page as markdown, tables as html, with page
    headers, footers and page numbers written in place as comments (`<!-- PageHeader: ... -->`), which
    a reader never sees. So:

    - `html` is that markdown with those comments unwrapped into their text, where Azure put them: the
      header is in Azure's document, marked as one, and the unwrapping moves and rebuilds nothing; and
    - `blocks` are its paragraphs (with their `role`: title, sectionHeading, pageHeader, pageFooter,
      pageNumber, footnote, or none), tables and figures. A paragraph inside a table's span is a cell's
      text, already in the table's block, and is left out.

    Boxes come as `source`, `D(page,x1,y1,...,x4,y4)`, in the page's unit (inches for a PDF). Azure
    states pages used, not a cost, so the cost is unknown.

    Auth: AZURE_CU_KEY. The resource is the `endpoint` option, not an environment variable: it
    decides where the page is analyzed, so it is a setting the run records.

        opb run --providers azure --sample 20 \
            --options '{"azure": {"endpoint": "https://<resource>.services.ai.azure.com"}}'
    """

    endpoint: str = dataclasses.field(
        default="", metadata={"help": "the Azure resource, e.g. https://<resource>.services.ai.azure.com"})
    analyzer: str = dataclasses.field(default="prebuilt-layout",
                                      metadata={"help": "Content Understanding's layout analyzer"})
    api_version: str = API_VERSION
    poll_interval: float = 2.0

    def __post_init__(self):
        object.__setattr__(self, "endpoint", self.endpoint.rstrip("/"))

    name: ClassVar[str] = "azure"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    workers: ClassVar[int] = 3

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Azure) -> list[contract.Request]:
    """One call for every output: headers are comments in Azure's markdown, unwrapped for html."""
    sent = {"analyzer": config.analyzer, "api_version": config.api_version}
    if "html" in wants:
        sent["derived"] = {"html": "Azure's markdown with its PageHeader, PageFooter and PageNumber "
                                   "comments unwrapped in place"}
    return [contract.Request(wants & SUPPORTS, sent)]


def box(source: str) -> tuple[int, tuple[float, float, float, float]] | None:
    """The page and bounding box `[x0, y0, x1, y1]` of a `D(page,x1,y1,...)` source."""
    if not (m := SOURCE.match(source or "")): return None
    xy = [float(v) for v in m[2].split(",")]
    xs, ys = xy[0::2], xy[1::2]
    return int(m[1]), (min(xs), min(ys), max(xs), max(ys))


def layout_blocks(content: dict) -> list[dict]:
    """Paragraphs outside tables, tables and figures as the `blocks` output, in the page's frame."""
    pages = {p["pageNumber"]: p for p in content.get("pages") or []}
    if not (page := pages.get(1)) or not (page.get("width") and page.get("height")):
        raise errors.VendorError(f"no size for page 1: {str(list(pages.values()))[:200]}", status=200)
    frame = (page["width"], page["height"])
    tables = [t.get("span") or {} for t in content.get("tables") or []]

    def inside(span: dict) -> bool:
        o = span.get("offset", -1)
        return any(t.get("offset", 0) <= o < t.get("offset", 0) + t.get("length", 0) for t in tables)

    kinds = [("", p, p.get("content") or "") for p in content.get("paragraphs") or []
             if not inside(p.get("span") or {})]
    kinds += [("table", t, " ".join(c.get("content") or "" for c in t.get("cells") or []))
              for t in content.get("tables") or []]
    kinds += [("figure", f, "") for f in content.get("figures") or []]
    out = []
    for kind, x, text in kinds:
        if not (found := box(x.get("source") or "")) or found[0] != 1: continue
        vendor_type = kind or x.get("role") or ""
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", text)).strip()
        out.append(layout.block(layout.label(LABELS, vendor_type), found[1], frame, plain))
    return out


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Azure | None = None) -> contract.Call:
    """Analyze the page, poll until it is done, return the analysis."""
    config = config or Azure()
    key = os.environ.get("AZURE_CU_KEY")
    if not key or not config.endpoint:
        raise errors.MissingCredential(
            "azure needs AZURE_CU_KEY in the environment and its resource in the options: "
            """--options '{"azure": {"endpoint": "https://<resource>.services.ai.azure.com"}}'""")
    deadline = budget.Budget(timeout)
    url = (f"{config.endpoint}/contentunderstanding/analyzers/{config.analyzer}:analyzeBinary"
           f"?api-version={config.api_version}")
    polls = 0
    with httpx.Client(headers={"Ocp-Apim-Subscription-Key": key}, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        r = client.post(url, content=page.read_bytes(), headers={"Content-Type": media},
                        timeout=deadline.timeout(300))
        if r.status_code >= 400 or not (op := r.headers.get("Operation-Location")):
            raise errors.VendorError(f"analyze HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        with adapter.reading("the analysis's id"):
            job_id = contract.json_object(r).get("id")
        retry = budget.PollRetry(deadline)
        with errors.job(job_id):
            while True:
                deadline.check(f"analysis {job_id} was still running after {polls} polls")
                try:
                    r = client.get(op, timeout=deadline.timeout(120))
                except httpx.TransportError as exc:
                    if retry.again(): continue
                    raise errors.VendorError(f"polling failed: {exc}"[:300], status=None) from None
                if r.status_code != 200:
                    if retry.again(r.status_code): continue
                    raise errors.VendorError(f"HTTP {r.status_code}: {r.text[:300]}",
                                             status=r.status_code, body=r.text)
                retry.reset()
                polls += 1
                with adapter.reading("the analysis's status"):
                    body = contract.json_object(r)
                if str(body.get("status")).lower() in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            if str(body.get("status")).lower() != "succeeded":
                raise errors.VendorError(f"analysis {body.get('status')}: {str(body.get('error'))[:300]}",
                                         status=200, raw=body)
    return contract.Call(body, cost=contract.Cost(), job_id=job_id)


def parse(raw: dict, request: contract.Request, config: Azure | None = None) -> tuple[dict, dict]:
    """The outputs in a finished analysis: markdown with header comments unwrapped, and blocks."""
    contents = (raw.get("result") or {}).get("contents") or []
    if not contents:
        raise errors.VendorError(f"succeeded with no contents: {str(raw)[:300]}", status=200)
    md = contents[0].get("markdown") or ""
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html": outputs[o] = markdown.to_html(PAGE_MARKER.sub(lambda m: m[1], md))
        if o == "blocks":
            try: outputs[o] = layout_blocks(contents[0])
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
