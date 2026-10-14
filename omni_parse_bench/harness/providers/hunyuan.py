"""HunyuanOCR-1.5 (tencent/HunyuanOCR), served from providers/oss/hunyuan/ on any GPU host.

Run as its repository's client runs it (github.com/Tencent-Hunyuan/HunyuanOCR at 1ef4179,
inference/vLLM/infer_vllm_client.py). Steps 3 and 4 run on the server (oss/hunyuan/server.py); steps 1
and 5 run here, with no vendor code.

How a page is processed:

  1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the repository takes
                          images only, so the page is rendered as for every model without a renderer of
                          its own.
  2. Image preprocessing  the model's own image processor, in vLLM (up to about 4.2M pixels).
  3. Model inference      the vendor's validated setup: vLLM 0.18.1 on Python 3.10, the weights at
                          revision 47644ecc with the repository's previous config.json (revision
                          3d3cbc9e; the current one targets transformers 5 and doesn't load correctly
                          in vLLM 0.18.1). An empty system message, then the page image and the
                          task's prompt from inference/utils/tasks.py; temperature 0, top_p 1, top_k
                          -1, repetition_penalty 1.08, special tokens skipped, at most 32768 tokens;
                          streamed, with the client's tail-repetition early stop (`infer_stream`).
  4. Vendor output parsing  the client's `clean_repeated_substrings`; for `doc_parse`, its
                          `normalize_doc_parse_markdown`.
  5. Mapping to opb outputs  the `layout_parse` reply is a JSON list of `{layout_type, bbox, text}`,
                          boxes as points on a 0-1000 grid: html is the items' texts in order, a
                          picture's text as the image's alt text; blocks are the items, each label from
                          LABELS.

`task` picks the client's task type: `layout_parse` (full-page parsing with layout analysis: the task
that reads the whole page and gives blocks; the default) or `doc_parse` (full-page parsing, page headers
and footers left out by its prompt; html only).

Differences from the vendor:

  - `layout_parse`, not the `doc_parse` Tencent scores document parsing with: `doc_parse` drops headers
    and footers and gives no boxes, and the benchmark scores both;
  - the vLLM 0.18.1 setup, which Tencent now lists as archived but validated (its unified environment,
    vLLM 0.25.1 on CUDA 13, is verified to align); and
  - each page has the benchmark's 900 s.

    docker build -t opb-hunyuan omni_parse_bench/harness/providers/oss/hunyuan
    docker run --gpus all -p 8001:8001 opb-hunyuan
    opb predict --provider hunyuan-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import base64
import dataclasses
import json
import os
import re
from pathlib import Path

from ... import markdown
from .. import budget, contract, errors, http, layout
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "tencent/HunyuanOCR@47644ecc4fc854efa4f505155158831f36773ee4"
TASKS = ("layout_parse", "doc_parse")


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the HunyuanOCR server (oss/hunyuan/) answers, the client's task, and its sampling (the
    client's by default)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    task: str = dataclasses.field(default="layout_parse", metadata={"choices": list(TASKS)})
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 32768
    repetition_penalty: float = 1.08
    min_repeats: int = 8
    long_edge: int = llm.LONG_EDGE

    def __post_init__(self):
        if self.task not in TASKS:
            raise ValueError(f"task must be one of {TASKS}, not {self.task!r}")


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers every output; `doc_parse` gives no blocks."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "settings": http.settings(config), "top_k": -1,
            "stream_early_stop": "infer_stream",
            "doc_postprocess": config.task == "doc_parse"}
    supports = SUPPORTS if config.task == "layout_parse" else frozenset({"html"})
    return [contract.Request(frozenset(wants) & supports, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    # Note: the repository takes images only, so the page goes as opb's PNG, in the body every server takes.
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "settings": http.settings(config, "long_edge")}
    return contract.Call(http.post(f"{config.base_url.rstrip('/')}/parse", body, budget.Budget(timeout),
                                   key=os.environ.get("OPB_ENDPOINT_KEY")))


# The layout_parse categories onto views.LABELS: the names the vendor's own layout scorer canonicalises
# (train_verl/reward/task_scorers/layout.py `_normalize_category`) and those seen in its answers. A
# category not here fails `blocks` only.
LABELS = {
    "paragraph": "text", "paragraph_span": "text", "para": "text", "text": "text", "abstract": "text",
    "reference": "text", "aside_text": "text", "table_of_contents": "text", "content": "text",
    "doc_title": "heading", "title": "heading", "para_title": "heading", "section_title": "heading",
    "sub_title": "heading", "heading": "heading",
    "header": "page_furniture", "footer": "page_furniture", "page": "page_furniture",
    "page_number": "page_furniture", "page_header": "page_furniture", "page_footer": "page_furniture",
    "list": "list", "list_item": "list",
    "figure_title": "caption", "table_title": "caption", "chart_title": "caption", "caption": "caption",
    "figure_caption": "caption", "table_caption": "caption",
    "footnote": "footnote", "table_footnote": "footnote", "page_footnote": "footnote",
    "figure_footnote": "footnote",
    "formula": "equation", "equation": "equation", "formula_number": "equation",
    "code": "code", "algorithm": "code",
    "table": "table",
    "figure": "figure", "chart": "figure", "image": "figure", "seal": "figure", "stamp": "figure",
    "signature": "figure",
    # also emitted by the model, though not in its scorer's list
    "none": "text", "partial_para": "text",
    "table_header_note": "caption", "table_both": "caption",
    "table_footer_note": "footnote",
    "watermark": "page_furniture",
    "checkbox": "form", "check": "form", "box": "form", "radio_button": "form", "radio_button_span": "form",
    "form": "form",
    "algorithm_chart": "figure",
}
_POINT = re.compile(r"\(\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*\)")
_TAG = re.compile(r"<[^>]+>")


def items(said: str) -> list[dict]:
    """The reply's JSON list of {layout_type, bbox, text}; a reply cut short by the early stop keeps
    every complete item before the cut."""
    said = said.strip()
    try:
        got = json.loads(said)
        return [x for x in got if isinstance(x, dict)] if isinstance(got, list) else []
    except ValueError:
        pass
    out, dec, i = [], json.JSONDecoder(), said.find("{")
    while 0 <= i < len(said):
        try:
            obj, end = dec.raw_decode(said, i)
        except ValueError:
            break
        if isinstance(obj, dict): out.append(obj)
        i = said.find("{", end)
    return out


def blocks(said: str) -> list[dict]:
    out = []
    for x in items(said):
        pts = [(float(a), float(b)) for a, b in _POINT.findall(str(x.get("bbox") or ""))]
        if len(pts) < 2: continue
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        kind = str(x.get("layout_type") or "").strip().lower().replace(" ", "_").replace("-", "_")
        box = [min(xs), min(ys), max(xs), max(ys)]
        out.append(layout.block(layout.label(LABELS, kind), box, (1000, 1000),
                                " ".join(_TAG.sub(" ", str(x.get("text") or "")).split())))
    return out


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The client's text as the page and as blocks. A label LABELS lacks fails the blocks only."""
    text = raw["text"] or ""
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(page_text(text) if raw["task"] == "layout_parse" else text)
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = blocks(text)
        except errors.VendorError as exc:
            errs["blocks"] = f"the adapter couldn't read the answer: VendorError: {exc}"[:300]
    return outputs, errs


def page_text(said: str) -> str:
    """The page as markdown: the items' texts in their order, joined as paragraphs. A reply that is not
    the JSON list (no item parses) is taken as the page's markdown as it is."""
    got = items(said)
    if not got:
        return said
    parts = []
    for x in got:
        text = str(x.get("text") or "").strip()
        # Note: a picture's text (a description, a chart's data) is the model's account of it, so it is
        # the image's alt text, where every vendor's picture descriptions go.
        if LABELS.get(str(x.get("layout_type"))) == "figure":
            parts.append(markdown.alt(markdown.to_html(text)) if text else "")
        elif text:
            parts.append(text)
    return "\n\n".join(p for p in parts if p)
