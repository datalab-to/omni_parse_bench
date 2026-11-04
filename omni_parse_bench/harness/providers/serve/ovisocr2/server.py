"""OvisOCR2's server: steps 3 and 4 of providers/ovisocr2.py, as the model card's `OvisOCR2Parser` does them.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
SETTINGS = ("temperature", "max_tokens", "min_pixels", "max_pixels", "filter_imgtags")
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}
# The model card's prompt, verbatim: it begins with a newline, which follows the image in the chat template.
PROMPT = ('\nExtract all readable content from the image in natural human reading order and output the '
          'result as a single Markdown document. For charts or images, represent them using an HTML image '
          'tag: <'
          'img src="images/bbox_{left}_{top}_{right}_{bottom}.jpg" />, where left, top, right, bottom are '
          'bounding box coordinates scaled to [0, 1000). Format formulas as LaTeX. Format tables as HTML: '
          '<table>...</table>. Transcribe all other text as standard Markdown. Preserve the original text '
          'without translation or paraphrasing.')


def clean_truncated_repeats(text: str, min_text_len: int = 8000, max_period: int = 200, min_period: int = 1,
                            min_repeat_chars: int = 100, min_repeat_times: int = 5) -> str:
    """The card's `_clean_truncated_repeats`, verbatim."""
    n = len(text)
    if n < min_text_len:
        return text
    max_period = min(max_period, n - 1)
    for unit_len in range(min_period, max_period + 1):
        if text[n - 1] != text[n - 1 - unit_len]:
            continue
        match_len = 1
        idx = n - 2
        while idx >= unit_len and text[idx] == text[idx - unit_len]:
            match_len += 1
            idx -= 1
        total_len = match_len + unit_len
        repeat_times = total_len // unit_len
        tail_len = total_len % unit_len
        if repeat_times >= min_repeat_times and total_len >= min_repeat_chars:
            return text[: n - total_len + unit_len] + text[n - tail_len:]
    return text


def drop_image_tags(text: str) -> str:
    """The card's `filter_imgtags`: blocks that are only a visual region's tag are dropped."""
    keep = (b for b in text.split("\n\n") if not b.strip().startswith('<img src="images/bbox_'))
    return "\n\n".join(keep)


def parse(png: bytes, s: dict) -> dict:
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    body = {"model": "ovisocr2", "temperature": s["temperature"], "max_tokens": s["max_tokens"],
            "messages": [{"role": "user", "content": [{"type": "image_url", "image_url": {"url": url}},
                                                      {"type": "text", "text": PROMPT}]}],
            "mm_processor_kwargs": {"images_kwargs": {"min_pixels": s["min_pixels"],
                                                       "max_pixels": s["max_pixels"]}},
            "chat_template_kwargs": {"enable_thinking": False}}
    r = httpx.post(f"{VLLM}/chat/completions", json=body, timeout=TIMEOUT_S)
    r.raise_for_status()
    completion = r.json()
    choice = completion["choices"][0]
    text = (choice["message"]["content"] or "").strip()
    if s["filter_imgtags"]:
        text = drop_image_tags(text)
    return {"text": clean_truncated_repeats(text), "finish_reason": choice.get("finish_reason"),
            "completion": completion}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """The card's request and post-processing, around the vLLM serving the model; how a page is processed is
    set out step by step in the adapter's docstring.

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 image file, "suffix", "settings": {"temperature", "max_tokens",
                        "min_pixels", "max_pixels", "filter_imgtags"}}
                        -> {"text": the cleaned reply, "finish_reason",
                        "completion": vLLM's reply as it came}"""
    def do_GET(self):
        if self.path == "/served": return self._send(200, SERVED)
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/parse":
            return self._send(404, {"error": f"no route {self.path}"})
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"})
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(200, {**parse(base64.b64decode(body["page"]), settings(body)), "served": SERVED})
        except KeyError as exc:
            self._send(400, {"error": f"{exc}"})
        except httpx.TimeoutException as exc:
            self._send(504, {"error": f"vLLM timed out: {exc}"})
        except httpx.HTTPStatusError as exc:
            self._send(502, {"error": f"vLLM answered {exc.response.status_code}: {exc.response.text[:300]}"})
        except Exception as exc:  # noqa: BLE001 - every failure goes back to the client as an answer
            self._send(500, {"error": f"{type(exc).__name__}: {exc}"[:500]})

    def _send(self, status: int, body: dict):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8001)
    ThreadingHTTPServer(("0.0.0.0", ap.parse_args().port), Handler).serve_forever()
