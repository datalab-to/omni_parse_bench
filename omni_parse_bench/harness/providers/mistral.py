"""Mistral OCR adapter: one POST /v1/ocr, answered in the same response.

The adapter is `Mistral`; its docstring says how a page is processed, and how to serve and run it.
"""
from __future__ import annotations

import base64
import dataclasses
import re
from pathlib import Path
from typing import Any, ClassVar

import httpx
from omni_bench_core import adapter

from ... import markdown
from .. import budget, contract, errors, layout
from ..adapter import PageAdapter

DEFAULT_BASE_URL = "https://api.mistral.ai"
SUPPORTS = frozenset({"html", "blocks"})
MEDIA = {".pdf": "application/pdf", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg"}
# Note: Mistral's documented block types.
LABELS = {
    "text": "text", "title": "heading", "list": "list", "caption": "caption", "code": "code",
    "references": "text", "aside_text": "text", "header": "page_furniture", "footer": "page_furniture",
    "equation": "equation",
    "table": "table", "image": "figure", "signature": "figure",
}
_TABLE = re.compile(r"\[(tbl-\d+\.\w+)\]\(\1\)")
_IMAGE = re.compile(r"!\[(img-\d+\.\w+)\]\(\1\)")


@dataclasses.dataclass(frozen=True)
class Mistral(PageAdapter):
    """The mistral adapter. Its fields are what mistral can be asked.

    One call produces both outputs. Mistral returns each page as markdown, with tables (asked for
    as html) and images left as placeholders (`[tbl-0.html](tbl-0.html)`, `![img-0.jpeg](img-0.jpeg)`)
    whose content is in the page's `tables` and `images`; asked to, it moves the page's header and
    footer out of the markdown into `header` and `footer`; and it returns paragraph-level `blocks`, each
    typed (text, title, table, image, header, footer, ...) with a box in the page's pixels. So:

    - `html` is the header, the markdown and the footer, joined in that order, tables put in place of
      their placeholders; the request's `sent` says so; and
    - `blocks` are its blocks, their text with tags removed as for every vendor.

    Images are found but not sent back (`include_image_base64` off): their pixels are no page text, and
    their placeholders (`![img-0.jpeg](img-0.jpeg)`) are taken out of the markdown, while their regions
    stay in the blocks. (`image_limit` 0 would drop those regions too.) Mistral states pages
    processed, not a cost, so the cost is unknown.

    Auth: MISTRAL_API_KEY.

        opb run --system mistral --sample 20
    """

    # Note: a dated model, not mistral-ocr-latest, so a run records the model it used.
    model: str = dataclasses.field(default="mistral-ocr-4-1", metadata={"help": "Mistral's OCR model"})
    base_url: str = DEFAULT_BASE_URL

    name: ClassVar[str] = "mistral"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    keys: ClassVar[tuple[str, ...]] = ("MISTRAL_API_KEY",)

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Mistral) -> list[contract.Request]:
    """One call for every output: the header and footer come apart, and are put back for html."""
    sent = {"model": config.model, "table_format": "html", "extract_header": True, "extract_footer": True,
            "include_blocks": True, "include_image_base64": False}
    if "html" in wants:
        sent["derived"] = {"html": "Mistral's header, markdown and footer, joined in that order"}
    return [contract.Request(wants & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Mistral | None = None) -> contract.Call:
    """Send the page inline, return the OCR response."""
    config = config or Mistral()
    key = errors.key("MISTRAL_API_KEY", "mistral")
    deadline = budget.Budget(timeout)
    media = MEDIA.get(page.suffix.lower(), "application/pdf")
    url = f"data:{media};base64,{base64.b64encode(page.read_bytes()).decode()}"
    document = ({"type": "image_url", "image_url": url} if media.startswith("image/")
                else {"type": "document_url", "document_url": url})
    body = {k: v for k, v in request.sent.items() if k != "derived"} | {"document": document}
    try:
        r = httpx.post(f"{config.base_url.rstrip('/')}/v1/ocr", json=body,
                       headers={"Authorization": f"Bearer {key}"}, timeout=max(1.0, deadline.remaining()))
    except httpx.TimeoutException:
        raise errors.VendorTimeout(f"no answer within the call's {deadline.total:g} s") from None
    if r.status_code != 200:
        raise errors.VendorError(f"HTTP {r.status_code}: {r.text[:300]}", status=r.status_code, body=r.text)
    with adapter.reading("the OCR response"):
        body = contract.json_object(r)
    return contract.Call(body, cost=contract.Cost())


def page_markdown(page: dict) -> str:
    """The page's header, markdown and footer, joined, with its tables in place."""
    tables = {t["id"]: t.get("content") or "" for t in page.get("tables") or []}
    body = _IMAGE.sub("", _TABLE.sub(lambda m: tables.get(m[1], m[0]), page.get("markdown") or ""))
    return "\n\n".join(p for p in (page.get("header"), body, page.get("footer")) if p)


def layout_blocks(page: dict) -> list[dict]:
    """The page's blocks as the `blocks` output, in the page's pixel frame."""
    dims = page.get("dimensions") or {}
    if not (dims.get("width") and dims.get("height")):
        raise errors.VendorError(f"no size for the page: {dims}", status=200)
    out = []
    for b in page.get("blocks") or []:
        corners = (b["top_left_x"], b["top_left_y"], b["bottom_right_x"], b["bottom_right_y"])
        plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", b.get("content") or "")).strip()
        out.append(layout.block(layout.label(LABELS, b.get("type") or ""), corners,
                                (dims["width"], dims["height"]), plain))
    return out


def parse(raw: dict, request: contract.Request, config: Mistral | None = None) -> tuple[dict, dict]:
    """The outputs in an OCR response: the page with its header and footer, and its blocks."""
    if not (pages := raw.get("pages")):
        raise errors.VendorError(f"no pages in the answer: {str(raw)[:300]}", status=200)
    page = pages[0]
    outputs, errs = {}, {}
    for o in request.outputs:
        if o == "html": outputs[o] = markdown.to_html(page_markdown(page))
        if o == "blocks":
            try: outputs[o] = layout_blocks(page)
            except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
                errs[o] = errors.unread(exc)
    return outputs, errs
