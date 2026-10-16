"""Unstructured adapter (Transform API): POST /api/v2/parse, poll /api/v2/jobs/<id>.

One call produces both outputs. Transform returns the page as typed elements (Title, NarrativeText,
ListItem, Table, Header, Footer, PageNumber, Image, FigureCaption, Form, ...), each with its text,
its box in the page's pixels (`metadata.coordinates`, with the frame as `layout_width` and
`layout_height`) and, for a table, its html (`metadata.text_as_html`). Boxes and table html are
returned only when asked for: `include=coordinates` and `include=table_html`, query parameters
repeated on the submit and on the poll, with `output=elements` on both (a poll without them answers
the server's default, markdown). So:

- `html` is the elements in order, each as its own html: a table as its `text_as_html`, a title as
  a heading, consecutive list items as one list, and every other element as a paragraph of its
  text, escaped. Page headers, footers and page numbers are kept where they sit; and
- `blocks` are the elements with a box. An element with none (rare) has no block.

`PageBreak` marks where a page ends and holds no text; it is left out of both. The profile is `best`,
Transform's most accurate. The response states no cost (Transform bills per page), so cost is
`Cost()`.

Auth: UNSTRUCTURED_API_KEY.

    opb predict --provider unstructured --page page.pdf --options '{"profile": "balanced"}'
"""
from __future__ import annotations

import dataclasses
import html
import os
import time
from pathlib import Path

import httpx

from .. import budget, contract, errors, layout

DEFAULT_BASE_URL = "https://transform.unstructured.io"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
INCLUDE = ("coordinates", "table_html")
# Note: Unstructured's documented element types. Image is a picture region (its text is the words
# printed in it); Form is a form region, as Datalab's Form.
LABELS = {
    "NarrativeText": "text", "UncategorizedText": "text", "Text": "text", "Address": "text",
    "EmailAddress": "text",
    "Title": "heading",
    "Header": "page_furniture", "Footer": "page_furniture", "PageNumber": "page_furniture",
    "ListItem": "list",
    "FigureCaption": "caption",
    "Footnote": "footnote",
    "Formula": "equation",
    "CodeSnippet": "code",
    "Table": "table",
    "Form": "form", "FormKeysValues": "form",
    "Image": "figure", "Figure": "figure", "Picture": "figure",
}
SKIPPED = frozenset({"PageBreak"})
TAGS = {"Title": "h2"}
RUNNING = frozenset({"queued", "processing"})
DONE = frozenset({"completed", "completed_with_warnings"})


@dataclasses.dataclass(frozen=True)
class Config:
    """What unstructured can be asked."""

    profile: str = dataclasses.field(
        default="best", metadata={"choices": ["balanced", "best"],
                                  "help": "best is Transform's most accurate profile"})
    base_url: str = DEFAULT_BASE_URL
    poll_interval: float = 3.0


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call for every output."""
    if not wants: return []
    sent = {"output": "elements", "profile": config.profile, "include": list(INCLUDE)}
    if "html" in wants:
        sent["derived"] = {"html": "the elements in order, each as html: a table as its text_as_html, a "
                                   "title as h2, list items as a ul, any other as a p of its text"}
    return [contract.Request(wants & SUPPORTS, sent)]


def page_html(elements: list[dict]) -> str:
    """The elements as one html page, in their order."""
    parts, in_list = [], False
    for e in elements:
        kind, text = e.get("type") or "", html.escape(e.get("text") or "")
        if kind in SKIPPED: continue
        if kind == "ListItem":
            if not in_list: parts.append("<ul>")
            parts.append(f"<li>{text}</li>")
            in_list = True
            continue
        if in_list: parts.append("</ul>")
        in_list = False
        table = (e.get("metadata") or {}).get("text_as_html") if kind == "Table" else None
        tag = TAGS.get(kind, "p")
        parts.append(table or f"<{tag}>{text}</{tag}>")
    if in_list: parts.append("</ul>")
    return "\n".join(parts)


def layout_blocks(elements: list[dict]) -> list[dict]:
    """The elements with a box as the `blocks` output, in the frame of the page's pixels."""
    out = []
    for e in elements:
        kind = e.get("type") or ""
        coords = (e.get("metadata") or {}).get("coordinates") or {}
        points = coords.get("points") or []
        if kind in SKIPPED or not points: continue
        frame = (coords.get("layout_width"), coords.get("layout_height"))
        if not all(frame):
            raise errors.VendorError(f"a box with no frame: {str(coords)[:200]}", status=200)
        xs, ys = [p[0] for p in points], [p[1] for p in points]
        corners = (min(xs), min(ys), max(xs), max(ys))
        out.append(layout.block(layout.label(LABELS, kind), corners, frame, e.get("text") or ""))
    return out


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Config | None = None) -> contract.Call:
    """Submit the page, poll until the job is done, return the finished job with its elements."""
    config = config or Config()
    key = os.environ.get("UNSTRUCTURED_API_KEY")
    if not key:
        raise errors.MissingCredential("UNSTRUCTURED_API_KEY is not set")
    deadline = budget.Budget(timeout)
    base_url = config.base_url.rstrip("/")
    sent = request.sent
    # Note: `include` is a repeated query parameter, not a form field, on both routes.
    query = [("include", i) for i in sent["include"]]
    polls = 0
    with httpx.Client(headers={"unstructured-api-key": key}, timeout=120) as client:
        media = MEDIA.get(page.suffix.lower(), "application/pdf")
        # Note: `Prefer: wait=0` returns the job at once; the poll below waits within the budget.
        r = client.post(f"{base_url}/api/v2/parse", params=query, headers={"Prefer": "wait=0"},
                        files={"input": (contract.upload_name(page), page.read_bytes(), media)},
                        data={"output": sent["output"], "profile": sent["profile"]},
                        timeout=deadline.timeout(300))
        if r.status_code not in (200, 202) or not (job_id := r.json().get("id")):
            raise errors.VendorError(f"parse HTTP {r.status_code}: {r.text[:300]}",
                                     status=r.status_code, body=r.text)
        retry = budget.PollRetry(deadline)
        with errors.job(job_id):
            while True:
                deadline.check(f"job {job_id} was still running after {polls} polls")
                try:
                    r = client.get(f"{base_url}/api/v2/jobs/{job_id}",
                                   params=[("output", sent["output"]), *query], timeout=deadline.timeout(120))
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
                if job.get("status") not in RUNNING: break
                time.sleep(min(config.poll_interval, deadline.remaining()))
            if job.get("status") not in DONE:
                why = f"job {job.get('status')}: {str(job.get('error'))[:300]}"
                raise errors.VendorError(why, status=200, raw=job)
    return contract.Call(job, job_id=job_id)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The outputs in a completed job: its elements as html, and as blocks."""
    elements = (raw.get("result") or {}).get("elements")
    if elements is None:
        raise errors.VendorError(f"completed with no elements: {str(raw)[:300]}", status=200)
    elements = [e for e in elements if ((e.get("metadata") or {}).get("page_number") or 1) == 1]
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html":
            outputs[o] = page_html(elements)
        if o == "blocks":
            try: outputs[o] = layout_blocks(elements)
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
