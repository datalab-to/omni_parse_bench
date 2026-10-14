"""Nanonets-OCR2-3B (nanonets/Nanonets-OCR2-3B), served by vLLM from providers/oss/nanonets/ on any GPU host.

Run as its model card runs it (huggingface.co/nanonets/Nanonets-OCR2-3B, "Using vLLM"). Its vendor
offers only the model, with no code of its own around it, so every step runs here, asking vLLM
directly.

How a page is processed:

  1. Input loading        the LLM adapter's PNG, its long edge at most 2048 px: the model card documents
                          image input only, so the page is rendered as for every model without a
                          renderer of its own.
  2. Image preprocessing  the model's own image processor, in vLLM.
  3. Model inference      `vllm serve` with no other flags, as the card does; the page image, then its
                          documented prompt, temperature 0, repetition penalty 1.0 (its tip for complex
                          tables; vLLM would otherwise apply the 1.05 of its generation_config.json),
                          at most 15000 tokens; asked once.
  4. Vendor output parsing  none: the reply is markdown with tables as HTML, and the model's own tags:
                          an image's description or caption in `<img>...</img>`, `<watermark>`,
                          `<page_number>` and `<signature>`.
  5. Mapping to opb outputs  html is the page through `markdown.to_html`, a figure description as the
                          image's alt text and the other tags unwrapped to their text. The model draws
                          no layout: `html` only.

Differences from the vendor:

  - each page has the benchmark's 900 s.

    docker build -t opb-nanonets omni_parse_bench/harness/providers/oss/nanonets
    docker run --gpus all -p 8001:8001 opb-nanonets
    opb predict --provider nanonets-ocr --page page.pdf --options '{"base_url": "http://localhost:8001"}'

OPB_ENDPOINT_KEY, if set, is sent as the bearer token the server requires.
"""
from __future__ import annotations

import dataclasses
import hashlib
import html as _html
import re
from pathlib import Path

from ... import markdown
from .. import budget, contract, errors, http
from . import llm

SUPPORTS = frozenset({"html"})
MODEL = "nanonets/Nanonets-OCR2-3B"
# The model card's prompt, verbatim.
PROMPT = (
    "Extract the text from the above document as if you were reading it naturally. Return the tables in "
    "html format. Return the equations in LaTeX representation. If there is an image in the document and "
    "image caption is not present, add a small description of the image inside the <img></img> tag; "
    "otherwise, add the image caption inside <img></img>. Watermarks should be wrapped in brackets. Ex: "
    "<watermark>OFFICIAL COPY</watermark>. Page numbers should be wrapped in brackets. Ex: "
    "<page_number>14</page_number> or <page_number>9/22</page_number>. Prefer using ☐ and ☑ for check boxes."
)
_IMG = re.compile(r"<img>(.*?)</img>", re.S | re.I)
_UNWRAP = re.compile(r"</?(?:watermark|page_number|signature)>", re.I)


@dataclasses.dataclass(frozen=True)
class Config:
    """Where the server (oss/nanonets/) answers (its chat endpoint is vLLM's, under /v1), and its
    sampling (the model card's by default; top_p, which it leaves unset, at vLLM's 1.0)."""

    base_url: str = dataclasses.field(default="http://127.0.0.1:8001", metadata={"names_run": False})
    temperature: float = 0.0
    top_p: float = 1.0
    max_tokens: int = 15000
    # Note: 1.0, the model card's tip for complex tables; without it vLLM applies the 1.05 of the
    # model's generation_config.json.
    repetition_penalty: float = 1.0
    long_edge: int = llm.LONG_EDGE


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call, for the page as markdown; the model draws no layout."""
    if "html" not in wants: return []
    sent = {"model": MODEL, "prompt_sha": hashlib.sha256(PROMPT.encode()).hexdigest()[:12],
            "settings": http.settings(config),
            "page": "llm png"}
    return [contract.Request(frozenset({"html"}), sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Config) -> contract.Call:
    content = [llm.image_part(llm.image(page, config.long_edge)), {"type": "text", "text": PROMPT}]
    body = {"model": MODEL, "messages": [{"role": "user", "content": content}],
            "temperature": config.temperature, "top_p": config.top_p, "max_tokens": config.max_tokens,
            "extra_body": {"repetition_penalty": config.repetition_penalty}}
    body = llm.chat(f"{config.base_url.rstrip('/')}/v1", body, budget.Budget(timeout))
    return contract.Call(body, cost=llm.tokens([body]), job_id=body.get("id"))


def page(said: str) -> str:
    """The model's tags as plain HTML: a description as an image's alt text, the rest unwrapped."""
    said = _IMG.sub(lambda m: f'<img alt="{_html.escape(" ".join(m[1].split()), quote=True)}">', said)
    return _UNWRAP.sub("", said)


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    text = llm.content(raw)
    if not text.strip():
        raise errors.VendorError("the reply is empty", status=200)
    return {"html": markdown.to_html(page(text))}, {}
