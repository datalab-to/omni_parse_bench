"""Nemotron 3.5 Parse (nvidia/Nemotron-3.5-Parse), served from providers/serve/nemotron_parse/ on a GPU host.

Run as NVIDIA's own client runs it (the `nemotron_parse` package in the model repository at revision
62cb1e4, release 3.5.0.post7: `nemotron_parse.inference.DocumentParser`). Steps 3 and 4 run on the server
(serve/nemotron_parse/server.py); steps 1, 2 and 5 run here, with no vendor code.

How a page is processed:

  1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the client takes images
                          only (its CLI: "Render PDF pages to images before calling it"), so the page is
                          rendered as for every model without a renderer of its own.
  2. Image preprocessing  the model's own image processor, in vLLM (NaViT packing, at most 1664 x 2048).
  3. Model inference      vLLM 0.26.0 (the reference serving contract) with the model card's flags and
                          its plugin's one-token MTP; the client's `parse` at its default mode, `single`
                          (one full-page request), with its default prompt
                          `</s><s><predict_bbox><predict_classes><output_markdown><predict_text_in_pic>`
                          and its default sampling: temperature 0.2, top_k 50, top_p 1.0, repetition
                          penalty 1.05, seed 0, at most 8744 tokens (the settings of NVIDIA's own
                          ParseBench pipeline). `mode` `double` or `triple` adds the client's Table/Chart
                          crop passes, at its crop and detection settings. A reply cut at the token limit,
                          empty, or failed raises the client's `GenerationError`, and the page has no
                          output, as the client returns none (its default, strict).
  4. Vendor output parsing  the client's `postprocess_document` at its default options: blocks in
                          model order, each with its class, a box normalized to the image, its text and
                          its rendered content (tables as HTML, header rows inferred), and the page's
                          markdown.
  5. Mapping to opb outputs  html is the blocks' rendered contents in order, as the client's markdown
                          joins them (a Title as `#`, a Section-header as `##`), except that a Picture's
                          or a Chart's content (the text in the picture, a chart's data table) becomes
                          an image's alt text, as for every system. blocks are the blocks, each class
                          from LABELS, the box as given (0 to 1).

Differences from the vendor:

  - picture and chart contents are alt text, as for every system (the client's markdown has them inline);
  - each page has the benchmark's 900 s.

    docker build -t opb-nemotron-parse omni_parse_bench/harness/providers/serve/nemotron_parse
    docker run --gpus all -p 8001:8001 opb-nemotron-parse
    opb predict --provider nemotron-parse --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import base64
import dataclasses
from pathlib import Path

from ... import markdown, views
from .. import contract, errors, http, layout
from . import llm

SUPPORTS = frozenset({"html", "blocks"})
WEIGHTS = "nvidia/Nemotron-3.5-Parse@62cb1e4ba153d113ff64aaf2be6e068c377cf53c"
MODES = ("single", "double", "triple")
# The model's class tokens (its tokenizer's <class_*> entries, and <class_Chart>) onto views.LABELS, as
# the Datalab types of the same names map.
LABELS = {
    "Text": "text", "TOC": "text", "Bibliography": "text",
    "Title": "heading", "Section-header": "heading",
    "Page-header": "page_furniture", "Page-footer": "page_furniture",
    "List-item": "list", "Caption": "caption", "Footnote": "footnote", "Formula": "equation",
    "Code": "code", "Table": "table",
    "Picture": "figure", "Chart": "figure",
}
PICTURES = frozenset({"Picture", "Chart"})


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the Nemotron Parse server (serve/nemotron_parse/) answers, the client's mode, and the sampling
    of its full-page request (the client's defaults)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    mode: str = dataclasses.field(default="single", metadata={"choices": list(MODES)})
    temperature: float = 0.2
    top_k: int = 50
    top_p: float = 1.0
    repetition_penalty: float = 1.05
    seed: int = 0
    max_tokens: int = 8744
    long_edge: int = llm.LONG_EDGE

    def __post_init__(self):
        if self.mode not in MODES:
            raise ValueError(f"mode must be one of {MODES}, not {self.mode!r}")


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call answers every output."""
    if not wants: return []
    sent = {"weights": WEIGHTS, "client": "nemotron_parse.inference.DocumentParser (3.5.0.post7)",
            "settings": http.settings(config), "triple_regions": "union", "merge_policy": "alternatives",
            "postprocess": "PostprocessOptions() defaults", "page": "llm png"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    # Note: the client takes images only, so the page goes as opb's PNG, in the body every server takes.
    body = {"page": base64.b64encode(llm.image(page, config.long_edge)).decode("ascii"), "suffix": ".png",
            "settings": http.settings(config, "long_edge")}
    raw = http.parse(config, page, timeout, body=body)
    if raw.get("error"):
        # Note: the client's GenerationError (cut at its token limit, empty, or failed): the client
        # returns no document, so the page has none; the reply is kept in the record.
        raise errors.VendorError(f"the client returned no document: {raw['error']}"[:300], status=200,
                                 raw=raw, cost=llm.tokens(raw.get("responses") or []))
    return contract.Call(raw, cost=llm.tokens(raw.get("responses") or []))


def _plain(content: str) -> str:
    return " ".join(views.text(markdown.to_html(content)).split())


def page_markdown(doc: dict) -> str:
    """The page as markdown: each block's rendered content in model order, a picture's or a chart's as
    an image's alt text. A reply with no blocks is the client's markdown as it is."""
    blocks = doc.get("blocks") or []
    if not blocks:
        return doc.get("markdown") or ""
    parts = []
    for b in blocks:
        content = (b.get("content") or "").replace("<tbc>", "").strip()
        if not content:
            continue
        cls = b.get("class")
        if cls in PICTURES:
            parts.append(markdown.alt(markdown.to_html(content)))
        elif cls == "Title" and not content.startswith("#"):
            parts.append(f"# {content}")
        elif cls == "Section-header" and not content.startswith("#"):
            parts.append(f"## {content}")
        else:
            parts.append(content)
    return "\n\n".join(parts)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The client's document as the page and as blocks. A class LABELS lacks fails the blocks only."""
    doc = raw["document"]
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = markdown.to_html(page_markdown(doc))
    if "blocks" in request.outputs:
        try:
            outputs["blocks"] = [layout.block(layout.label(LABELS, b["class"]), b["bbox"], (1, 1),
                                              _plain(b.get("content") or ""))
                                 for b in doc.get("blocks") or []]
        except (errors.VendorError, KeyError, TypeError, ValueError) as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
