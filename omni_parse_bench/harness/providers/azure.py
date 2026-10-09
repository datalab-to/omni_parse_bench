"""Azure Content Understanding adapter: the prebuilt layout analyzer, POST :analyzeBinary, poll.

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

    opb predict --provider azure --page page.pdf \
        --options '{"endpoint": "https://<resource>.services.ai.azure.com"}'
"""
from __future__ import annotations

import dataclasses
import os
import re
import time
from pathlib import Path

import httpx

from ... import markdown
from .. import budget, contract, errors, layout

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
class Config:
    """What azure can be asked.

    `endpoint` has no default to give, since every Azure resource has its own; it is empty here, so
    a `Config` can be built (`opb providers`, a run's name), and `call` refuses it.
    """

    endpoint: str = dataclasses.field(
        default="", metadata={"help": "the Azure resource, e.g. https://<resource>.services.ai.azure.com"})
    analyzer: str = dataclasses.field(default="prebuilt-layout",
                                      metadata={"help": "Content Understanding's layout analyzer"})
    api_version: str = API_VERSION
    poll_interval: float = 2.0

    def __post_init__(self):
        object.__setattr__(self, "endpoint", self.endpoint.rstrip("/"))


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
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
         config: Config | None = None) -> contract.Call:
    """Analyze the page, poll until it is done, return the analysis."""
    config = config or Config()
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
        job_id = r.json().get("id")
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
                retry.ok()
                polls += 1
                body = r.json()
                if str(body.get("status")).lower() in TERMINAL: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            if str(body["status"]).lower() != "succeeded":
                raise errors.VendorError(f"analysis {body['status']}: {str(body.get('error'))[:300]}",
                                         status=200, raw=body)
    return contract.Call(body, cost=contract.Cost(), job_id=job_id)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
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
                errs[o] = f"blocks: {type(exc).__name__}: {exc}"
    return outputs, errs
