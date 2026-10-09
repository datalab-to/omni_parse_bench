"""Single-shot LLM parsing: the page image goes to the model, one call per output.

Used for vision-language models (GPT, Claude, ...) through any OpenAI-compatible endpoint. The
published runs use OpenRouter, which returns billed cost (`usage.cost`) rather than only a token
count. Every model gets the same prompts:

    html      transcribe the page as HTML, keeping everything printed on it
    blocks    the page's layout blocks, one JSON object per line, boxes on a 0-1000 grid as
              [ymin, xmin, ymax, xmax]

A reply that is markdown rather than HTML is converted by `markdown.to_html`, the same converter
every provider's markdown goes through. A reply that doesn't parse is asked for again.

No sampling setting is sent: each model runs at its own default temperature and reasoning, as every
vendor runs at its own settings (Google, for one, advises against lowering Gemini 3's temperature,
which can make it loop). The page image is sent at high detail, so no endpoint downscales it.

Auth: OPENROUTER_API_KEY, or OPENAI_API_KEY. Another endpoint is selected with the `base_url`
option, so the record says which endpoint answered.

    opb predict --provider openai/gpt-5.6-sol --page page.pdf

The model is the provider name; `--options {"model": ...}` is refused.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import io
import json
import os
import random
import re
import time
from pathlib import Path

import openai

from ... import markdown
from .. import budget, contract, errors, layout, raster

SUPPORTS = frozenset({"html", "blocks"})
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
LONG_EDGE = 2048      # pixels on the page image's long edge

TRANSCRIBE = """\
Transcribe this document page into HTML, faithfully and completely, in natural reading order.

- Keep every piece of text printed on the page, exactly as written: headings, body text, lists, \
captions, footnotes, and the page's running headers, footers and page numbers.
- Headings as <h1> to <h6>, paragraphs as <p>, bold as <b>, italic as <i>.
- Tables as <table>, with colspan and rowspan where cells are merged.
- Math as LaTeX: inline between $ and $, displayed between $$ and $$.
- Form checkboxes as ☐ (empty) or ☑ (ticked).
- Leave pictures out; don't describe them.

Return only the HTML."""
LAYOUT = """\
Segment this document page into layout blocks. Each block's type is one of:
- "heading": a title or section heading;
- "page_furniture": a running page header or footer, or a page number, in the top or bottom margin;
- "text": a paragraph of running text;
- "list": a list, or one item of a bulleted or numbered list;
- "caption": the caption of a figure or a table;
- "footnote": a note at the foot of the page or of a table;
- "equation": a displayed equation;
- "code": a code listing;
- "table": a table;
- "form": a region of form fields: labels with spaces, lines or boxes to fill in; or
- "figure": a picture, chart, diagram, drawing, logo or signature.
Output one JSON object per line (JSON Lines, no array, no markdown fence): {"type": <type>, \
"bbox_2d": [ymin, xmin, ymax, xmax], "text": <the block's full text on one line>}. bbox_2d is on a \
0-1000 scale of the page. For tables give the cell text in reading order; for figures only the text \
printed inside them, or "" if none. Blocks must not overlap and must be tight around their content. \
Every block on the page, nothing else."""
PROMPTS = {"html": TRANSCRIBE, "blocks": LAYOUT}
# The layout prompt names its types by the block kinds (views.LABELS).
LABELS = {k: k for k in ("heading", "page_furniture", "text", "list", "caption", "footnote", "equation",
                         "code", "table", "form", "figure")}


@dataclasses.dataclass(frozen=True)
class Config:
    """What a raw-model leg can be asked. `model` has no default: it IS the provider name."""

    model: str = dataclasses.field(metadata={"help": "an OpenRouter org/model id"})
    max_output_tokens: int = 32000
    base_url: str = DEFAULT_BASE_URL
    attempts: int = 3


def requests(wants: frozenset[str], config: Config) -> list[contract.Request]:
    """One call per output, each with its own prompt."""
    # Note: the prompt's digest is part of what was sent, so a changed prompt is a different run.
    sha = lambda o: hashlib.sha256(PROMPTS[o].encode()).hexdigest()[:12]  # noqa: E731
    return [contract.Request(frozenset({o}), {"model": config.model, "prompt": o, "prompt_sha": sha(o)})
            for o in sorted(wants)]


def image(page: Path) -> bytes:
    """The page as a PNG, its long edge at most LONG_EDGE pixels."""
    from PIL import Image

    if page.suffix.lower() == ".pdf":
        img = raster.render(page, lambda size: LONG_EDGE / max(size))
    else:
        img = Image.open(page)
        img.thumbnail((LONG_EDGE, LONG_EDGE))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG")
    return buf.getvalue()


_THINK = re.compile(r"<think>.*?</think>", re.S | re.I)
# Note: a line ending in a colon before the page, or any line before a fence naming html or markdown.
_PREAMBLE = re.compile(r"\A[^\n<`]*(?::[ \t]*\n+(?=<|```)|\n+(?=```(?:html|markdown|md)[ \t]*\n))", re.I)
_MARKDOWN = re.compile(r"(?m)^[ \t]{0,3}(?:#{1,6}[ \t]|\|.*\||[-*+][ \t]|\d{1,9}[.)][ \t])|\*\*\S")


def reply(text: str) -> str:
    """A reply's page: without leaked reasoning (<think>), a line introducing it ("Here is the
    transcription:") or a fence around it (`markdown.unwrapped`); a fenced listing inside it stays."""
    text = _PREAMBLE.sub("", _THINK.sub("", text).strip())
    return markdown.unwrapped(text).strip()


def as_html(text: str) -> str:
    """A reply as HTML. A reply that starts with a tag is HTML whatever it holds: `**` inside LaTeX
    (`^{**}`) is not markdown. Otherwise any markdown structure (a heading, a table row, a list item,
    **bold**) means markdown, which markdown.to_html converts with any HTML in it kept; only a reply
    with none is taken as HTML as it is."""
    text = reply(text)
    if text.startswith("<"): return text
    return markdown.to_html(text) if _MARKDOWN.search(text) or "<" not in text else text


def _objects(text: str) -> list:
    """The JSON values in a layout reply: a JSON array, or objects one per line or spread over lines.
    A line that isn't JSON is kept as a string, for `as_blocks` to salvage."""
    try:
        whole = json.loads(text)
        return whole if isinstance(whole, list) else [whole]
    except json.JSONDecodeError:
        pass
    out, i, decoder = [], 0, json.JSONDecoder()
    while i < len(text):
        if text[i].isspace() or text[i] in ",[]":
            i += 1
            continue
        try:
            obj, i = decoder.raw_decode(text, i)
            out.append(obj)
        except json.JSONDecodeError:
            end = text.find("\n", i)
            end = len(text) if end < 0 else end
            out.append(text[i:end])
            i = end
    return out


def as_blocks(text: str) -> list[dict] | None:
    """A layout reply as blocks, or None when it holds none. A line that isn't valid JSON is salvaged
    by its box, type and text, so one unescaped quote costs one block, not the page. A box is read
    under `bbox_2d` or `box_2d`, Gemini's own name for it."""
    out = []
    for obj in _objects(reply(text)):
        if isinstance(obj, str):
            box = re.search(r'"b(?:b)?ox_2d"\s*:\s*\[([^\]]+)\]', obj)
            kind = re.search(r'"type"\s*:\s*"([^"]*)"', obj)
            said = re.search(r'"text"\s*:\s*"(.*)"', obj)
            if not box: continue
            obj = {"type": kind.group(1) if kind else "text", "text": said.group(1) if said else "",
                   "bbox_2d": re.findall(r"-?[\d.]+", box.group(1))}
        if not isinstance(obj, dict): continue
        box = obj.get("bbox_2d", obj.get("box_2d"))
        # Note: a block given as a box per line ([[ymin, xmin, ymax, xmax], ...]) is one block, over their
        # union.
        if isinstance(box, list) and box and all(isinstance(b, list) and len(b) == 4 for b in box):
            box = [min(b[0] for b in box), min(b[1] for b in box),
                   max(b[2] for b in box), max(b[3] for b in box)]
        # Note: a malformed box costs its block, not the page.
        if not isinstance(box, list) or len(box) != 4: continue
        try: y0, x0, y1, x1 = (float(v) for v in box)
        except (TypeError, ValueError): continue  # one malformed box costs its block, not the page
        kind = str(obj.get("type", "text"))
        # Note: the prompt names our kinds; a type outside them (a model's own word) is read by its words.
        out.append(layout.block(LABELS.get(kind) or layout.guess(kind), [x0, y0, x1, y1], (1000, 1000),
                                str(obj.get("text", ""))))
    return out or None


def _cost(usage: dict) -> contract.Cost:
    """What the call cost. Under BYOK (the key's own provider account), `usage.cost` is only
    OpenRouter's fee and the model's price is billed by the provider, stated as
    `cost_details.upstream_inference_cost`; the cost is both."""
    tokens = {"tokens_in": usage.get("prompt_tokens"), "tokens_out": usage.get("completion_tokens")}
    upstream = (usage.get("cost_details") or {}).get("upstream_inference_cost")
    fee = usage.get("cost")
    if usage.get("is_byok") and isinstance(upstream, (int, float)) and isinstance(fee, (int, float)):
        return contract.Cost.reported(fee + upstream, "usage.cost + cost_details.upstream_inference_cost",
                                      **tokens)
    return contract.Cost.reported(usage.get("cost"), "usage.cost", **tokens)


def call(page: Path, request: contract.Request, *, timeout: float = 900.0,
         config: Config) -> contract.Call:
    """One completion for one output, asked again only for an answer that isn't usable.

    Only a reply that finished (`stop`) and parses is kept. One cut off by an error is asked again,
    and if every attempt is, the call fails for good: `predict` doesn't ask again. One cut at
    max_output_tokens is final, since a retry at the same limit can't fit either; one the provider
    refused (`content_filter`) is final too. The cost counts every attempt. Transport failures are
    not retried here, and the SDK's retries are off: `predict`'s retry decides, so the loops can't
    multiply.
    """
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
    if not key:
        raise errors.MissingCredential("OPENROUTER_API_KEY (or OPENAI_API_KEY) must be set")
    deadline = budget.Budget(timeout)
    # Note: the SDK's own retries are off; `predict` retries every vendor the same way.
    client = openai.OpenAI(base_url=config.base_url, api_key=key, max_retries=0)
    b64 = base64.b64encode(image(page)).decode("ascii")
    (output,) = request.outputs
    messages = [{"role": "user", "content": [
        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}", "detail": "high"}},
        {"type": "text", "text": PROMPTS[output]}]}]
    last, spent, cut = None, [], False
    for attempt in range(config.attempts):
        if attempt:
            time.sleep(min((2 ** attempt) + random.uniform(0, 1), deadline.remaining()))
        deadline.check(f"after {attempt} attempt(s) that produced no usable answer")
        try:
            resp = client.chat.completions.create(
                model=config.model, messages=messages, max_tokens=config.max_output_tokens,
                timeout=deadline.remaining(), extra_body={"usage": {"include": True}})
        except openai.APIStatusError as exc:
            raise errors.VendorError(f"HTTP {exc.status_code}: {str(exc)[:300]}", status=exc.status_code,
                                     body=str(exc.body), cost=contract.total(spent)) from None
        except openai.APIConnectionError as exc:
            raise errors.VendorUnreachable(f"connection failed: {exc}"[:300],
                                           cost=contract.total(spent)) from None
        body = last = resp.model_dump()
        spent.append(_cost(body.get("usage") or {}))
        finish = ((body.get("choices") or [{}])[0]).get("finish_reason")
        if finish == "length":
            raise errors.VendorError(f"the reply hit max_output_tokens ({config.max_output_tokens})",
                                     status=200, raw=body, cost=contract.total(spent), job_id=body.get("id"))
        if finish == "content_filter":
            raise errors.VendorError("the provider refused the page (content_filter)", status=200, raw=body,
                                     cost=contract.total(spent), job_id=body.get("id"))
        cut = cut or finish != "stop"
        if finish == "stop" and _usable(body, output):
            return contract.Call(body, cost=contract.total(spent), job_id=body.get("id"))
    raise errors.VendorError(f"no usable {output} after {config.attempts} attempts"
                             + (" (a reply was cut off by an error)" if cut else ""),
                             status=200, raw=last, cost=contract.total(spent))


def _usable(body: dict, output: str) -> bool:
    try:
        return bool(parse(body, contract.Request(frozenset({output}), {}), None)[0].get(output))
    except errors.VendorError:
        return False


def parse(raw: dict, request: contract.Request, config: Config | None = None) -> tuple[dict, dict]:
    """The one output in a finished reply: its text as HTML (`as_html`) or as blocks (`as_blocks`)."""
    (output,) = request.outputs
    choice = (raw.get("choices") or [{}])[0]
    if choice.get("finish_reason") != "stop":
        raise errors.VendorError(f"the reply didn't finish: {choice.get('finish_reason')}", status=200)
    text = (choice.get("message") or {}).get("content")
    value = (as_blocks(text) if output == "blocks" else as_html(text)) if text else None
    if not value:
        raise errors.VendorError(f"no usable {output} in the reply", status=200)
    return {output: value}, {}
