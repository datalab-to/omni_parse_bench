"""GLM-OCR's SDK servers behind one route: each page goes to a free one.

The SDK (github.com/zai-org/GLM-OCR, `glmocr[selfhosted,server]` 0.1.5) self-hosts as its README
documents: `python -m glmocr.server` runs PP-DocLayoutV3 layout detection, recognises each region with
the model (vLLM on localhost:8000, chosen by the GLMOCR_* environment), and formats the page. One SDK
server shares one pipeline between concurrent requests, and concurrent requests to one server came back
empty (60 pages: 10.1 at 64 in flight, 76.6 one at a time). So this starts GLM_SERVERS of them (12) on
ports 5002, 5003, ..., and gives each one page at a time; pages still run in parallel.

Every setting is the SDK's default config.yaml but its port, and, with GLM_SDK_CONFIG=keep (the
default here), one more: the default abandons the regions it labels header, footer, number, footnote,
aside_text, reference and header/footer images, so they would be in neither output. The benchmark
scores the whole page, headers and footers included, for every system, so `keep` reads those regions:
the text ones as text, the header and footer images as images. `default` runs the SDK as it ships.

    GET  /health                       200 once every SDK server is up
    POST /parse                        {"page": base64 file, "suffix": ".pdf" or the image's}
                                       -> the SDK's answer (`markdown_result`, `json_result`), with
                                       "sdk_config" and "vendor" (the SDK version) added; 503 when the SDK
                                       failed to read a region, which it would leave out silently

With OPB_ENDPOINT_KEY set, a request needs it as its bearer token. It exits when an SDK server does.
It runs in this folder's image (start.sh); the Dockerfile says how to build and run it.
"""
from __future__ import annotations

import argparse
import base64
import importlib.metadata
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import yaml

import glmocr

SERVERS = int(os.environ.get("GLM_SERVERS", "12"))
SDK_CONFIG = os.environ.get("GLM_SDK_CONFIG", "keep")
BASE_PORT = 5002
TIMEOUT_S = 900.0
KEY = os.environ.get("OPB_ENDPOINT_KEY")
VERSION = importlib.metadata.version("glmocr")
FREE: queue.Queue[str] = queue.Queue()
# The SDK's log lines for a region or page it failed to read and left out (pipeline/_workers.py).
FAILURES = ("Recognition failed", "Layout detection failed")


def config(port: int) -> dict:
    """The SDK's default config.yaml on `port`, with the abandoned regions read under `keep`."""
    cfg = yaml.safe_load((Path(glmocr.__file__).parent / "config.yaml").read_text())
    cfg["server"] = {**cfg["server"], "port": port}
    if SDK_CONFIG == "keep":
        # Note: only the documented label-to-task and label-to-type mappings change.
        lay, fmt = cfg["pipeline"]["layout"], cfg["pipeline"]["result_formatter"]
        text = ["header", "footer", "number", "footnote", "aside_text", "reference"]
        images = ["header_image", "footer_image"]
        lay["label_task_mapping"]["abandon"] = []
        lay["label_task_mapping"]["text"] += [x for x in text if x not in lay["label_task_mapping"]["text"]]
        lay["label_task_mapping"]["skip"] += [x for x in images if x not in lay["label_task_mapping"]["skip"]]
        vis = fmt["label_visualization_mapping"]
        vis["text"] += [x for x in text if x not in vis["text"]]
        vis["image"] += [x for x in images if x not in vis["image"]]
    elif SDK_CONFIG != "default":
        raise SystemExit(f"GLM_SDK_CONFIG is {SDK_CONFIG!r}; set it to keep or default")
    return cfg


def start() -> list[subprocess.Popen]:
    """The SDK servers, each up and answering /health."""
    procs = []
    for i in range(SERVERS):
        port = BASE_PORT + i
        (p := Path(f"/tmp/glmocr_{port}.yaml")).write_text(yaml.safe_dump(config(port)))
        procs.append(subprocess.Popen([sys.executable, "-m", "glmocr.server", "--config", str(p)],
                                      stdout=open(f"/tmp/glmocr_{port}.log", "w"), stderr=subprocess.STDOUT))
        time.sleep(3)
    for i, proc in enumerate(procs):
        port = BASE_PORT + i
        while True:
            if proc.poll() is not None:
                log = Path(f"/tmp/glmocr_{port}.log").read_text()[-3000:]
                raise SystemExit(f"SDK server {port} exited:\n{log}")
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health", timeout=5).status_code == 200: break
            except httpx.HTTPError:
                pass
            time.sleep(2)
        FREE.put(f"http://127.0.0.1:{port}")
    return procs


def watch(procs: list[subprocess.Popen]) -> None:
    """Exit the whole server when an SDK server exits, so its host sees the failure."""
    while all(p.poll() is None for p in procs):
        time.sleep(5)
    print("an SDK server exited", flush=True)
    os._exit(1)


class Dropped(Exception):
    """The SDK left a region out after its recognition failed."""


def parse(data: bytes, suffix: str) -> dict:
    """The SDK's answer for one page; Dropped when it failed to read part of it.

    The SDK drops a region whose recognition failed (a timeout, an error) from the page without saying
    so in its answer, only in its log. Each SDK server reads one page at a time, so its log while this
    page is read is this page's; a failure there makes the page fail, to be asked again, rather than
    come back with text missing."""
    server = FREE.get()
    log = Path(f"/tmp/glmocr_{server.rsplit(':', 1)[1]}.log")
    # Note: the SDK servers share this container, so the page goes as a file path, which the SDK's own
    # page loader opens: a PDF at its pdf_dpi, an image as it is.
    page = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    try:
        page.write(data)
        page.close()
        start = log.stat().st_size
        r = httpx.post(f"{server}/glmocr/parse", json={"images": [f"file://{page.name}"]}, timeout=TIMEOUT_S)
        r.raise_for_status()
        with log.open() as f:
            f.seek(start)
            failed = [line.strip() for line in f if any(m in line for m in FAILURES)]
        if failed:
            raise Dropped(f"the SDK dropped {len(failed)} region(s) it failed to read: {failed[0][:200]}")
        return {**r.json(), "sdk_config": SDK_CONFIG, "vendor": {"glmocr": VERSION}}
    finally:
        os.unlink(page.name)
        FREE.put(server)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self._send(200 if self.path == "/health" else 404, {"ok": self.path == "/health"})

    def do_POST(self):
        if self.path != "/parse":
            return self._send(404, {"error": f"no route {self.path}"})
        if KEY and self.headers.get("Authorization") != f"Bearer {KEY}":
            return self._send(401, {"error": "a bearer token (OPB_ENDPOINT_KEY) is needed"})
        try:
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self._send(200, parse(base64.b64decode(body["page"]), body["suffix"]))
        except Dropped as exc:
            self._send(503, {"error": str(exc)})
        except httpx.HTTPStatusError as exc:
            self._send(502, {"error": f"the SDK answered {exc.response.status_code}: "
                                      f"{exc.response.text[:300]}"})
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
    port = ap.parse_args().port
    threading.Thread(target=watch, args=(start(),), daemon=True).start()
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
