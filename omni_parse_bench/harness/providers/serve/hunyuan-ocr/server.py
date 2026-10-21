"""HunyuanOCR-1.5's server: steps 3 and 4 of providers/hunyuan.py, with its repository's client code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import openai
from inference.utils import output_utils, tasks

VLLM = os.environ.get("VLLM_URL", "http://127.0.0.1:8000/v1")
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
REPO = "/opt/hunyuan"
COMMIT = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True,
                        text=True).stdout.strip()
SAMPLING = ("temperature", "top_p", "max_tokens")
# Note: every request sets these, from the adapter's options (the vendor's values by default).
SETTINGS = SAMPLING + ("task", "repetition_penalty", "min_repeats")
CLIENT = openai.OpenAI(api_key="EMPTY", base_url=VLLM, timeout=TIMEOUT_S, max_retries=0)


# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}


def parse(png: bytes, s: dict) -> dict:
    task = s["task"]
    url = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
    common = {"model": "tencent/HunyuanOCR", **{k: s[k] for k in SAMPLING},
              "messages": [{"role": "system", "content": ""},
                           {"role": "user", "content": [
                               {"type": "image_url", "image_url": {"url": url}},
                               {"type": "text", "text": tasks.get_prompt(task)}]}],
              "extra_body": {"top_k": -1, "repetition_penalty": s["repetition_penalty"],
                             "skip_special_tokens": True}}
    text, early = output_utils.infer_stream(CLIENT, common, s["min_repeats"])
    text = output_utils.clean_repeated_substrings(text)
    if task == "doc_parse":
        text, _ = output_utils.normalize_doc_parse_markdown(text)
    return {"text": text, "early_stopped": early, "task": task, "vendor": {"HunyuanOCR": COMMIT}}


def settings(body: dict) -> dict:
    """The request's settings, exactly SETTINGS."""
    s = body["settings"]
    if set(s) != set(SETTINGS):
        raise ValueError(f"settings must name exactly {sorted(SETTINGS)}, not {sorted(s)}")
    return s


class Handler(BaseHTTPRequestHandler):
    """Its client's request, streaming early stop and post-processing, around the vLLM serving the model; how
    a page is processed is set out step by step in the adapter's docstring. The repository takes images only,
    so this takes the page as an image file. The client's utilities are imported from the repository, which
    the image clones (inference/ on PYTHONPATH).

        GET  /health    200 once up
        POST /parse     {"page": base64 image file, "suffix", "settings": {"task": "layout_parse" or
                        "doc_parse", "temperature", "top_p", "max_tokens", "repetition_penalty",
                        "min_repeats": the early stop's}}
                        -> {"text": the cleaned reply, "early_stopped", "task",
                        "vendor": {"HunyuanOCR": its commit}}"""
    def do_GET(self):
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
        except openai.APITimeoutError as exc:
            self._send(504, {"error": f"vLLM timed out: {exc}"})
        except openai.APIStatusError as exc:
            self._send(502, {"error": f"vLLM answered {exc.status_code}: {str(exc)[:300]}"})
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
