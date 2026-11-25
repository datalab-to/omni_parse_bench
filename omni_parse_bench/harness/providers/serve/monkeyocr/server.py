"""MonkeyOCR's server: steps 1 to 4 of providers/monkeyocr.py, with MonkeyOCR's own code.

`Handler` says what the server answers and how it runs.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from magic_pdf.data.data_reader_writer import FileBasedDataWriter
from magic_pdf.data.dataset import ImageDataset, PymuDocDataset
from magic_pdf.dict2md.ocr_mkcontent import get_title_level, merge_para_with_text
from magic_pdf.model.custom_model import MonkeyOCR
from magic_pdf.model.doc_analyze_by_custom_model_llm import doc_analyze_llm

CONFIG = os.environ.get("MONKEYOCR_CONFIG", "model_configs.yaml")
KEY = os.environ.get("OPB_ENDPOINT_KEY")
_model: MonkeyOCR | None = None
# Note: one page at a time, as the repository's own FastAPI does for a backend that isn't asynchronous: the
# model and its engine are shared.
_lock = threading.Lock()

# What it serves, as start.sh started it; in every reply.
SERVED = {"weights": os.environ.get("WEIGHTS"), "revision": os.environ.get("REVISION")}

# The sub-blocks of an image or a table block, in the middle JSON's own names.
_GROUPED = {"image": ("image_body", "image_caption", "image_footnote"),
            "table": ("table_body", "table_caption", "table_footnote")}


def model() -> MonkeyOCR:
    """The model, made on the first page: loading it takes minutes and /health answers meanwhile."""
    global _model
    with _lock:
        if _model is None:
            _model = MonkeyOCR(CONFIG)
        return _model


def table_html(block: dict) -> str:
    """A table body's html (its span's `html`), as `ocr_mk_markdown_with_para_core_v2` reads it."""
    return " ".join(s.get("html") or s.get("latex") or "" for ln in block.get("lines", [])
                    for s in ln.get("spans", []) if s.get("type") == "table")


# What PP-DocLayoutV2 labels that MonkeyOCR folds into its "abandon" category (PaddleXLayoutModel's
# category_mapping): with `--pred-abandon` they are read as text blocks, so the middle JSON no longer
# says which they were; `abandoned` recovers it from the layout model's own detections.
ABANDONED = frozenset({"number", "header", "header_image", "footer", "footer_image", "seal",
                       "formula_number"})


def abandoned(inferred, page_size) -> list[tuple[str, list[float]]]:
    """The abandon-category regions of the page, `(PP-DocLayoutV2 label, box)`, the box in the page's units
    (the detections are in the rendered image's pixels, scaled by page size over image size, as magic_model
    scales them)."""
    result = inferred.get_infer_res()[0]
    w, h = result["page_info"]["width"], result["page_info"]["height"]
    sx, sy = page_size[0] / w, page_size[1] / h
    out = []
    for det in result["layout_dets"]:
        if det.get("original_label") in ABANDONED:
            x0, y0, x1, y1 = det["poly"][0], det["poly"][1], det["poly"][4], det["poly"][5]
            out.append((det["original_label"], [x0 * sx, y0 * sy, x1 * sx, y1 * sy]))
    return out


def overlap(a: list[float], b: list[float]) -> float:
    """Intersection over union of two boxes."""
    w = min(a[2], b[2]) - max(a[0], b[0])
    h = min(a[3], b[3]) - max(a[1], b[1])
    if w <= 0 or h <= 0: return 0.0
    inter = w * h
    return inter / ((a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter)


def blocks(page: dict, regions: list[tuple[str, list[float]]] = ()) -> list[dict]:
    """The page's `para_blocks` as `{type, bbox, content, level?}`, in the middle JSON's reading order; an
    image or a table block gives its body, caption and footnote sub-blocks in turn, each with its own
    type. Text is the repository's own `merge_para_with_text`; a table body is its html. A `text` block
    whose box is mostly (IoU 0.5 or more) one of `regions`, the abandon-category detections, takes that
    detection's label as its type (`header`, `footer`, `number`, ...): with `--pred-abandon` the repository
    reads those regions as plain text and drops what they were."""
    out = []
    for b in page.get("para_blocks", []):
        parts = _GROUPED.get(b["type"])
        for s in (b.get("blocks", []) if parts else [b]):
            kind = s["type"]
            if kind == "table_body":
                content = table_html(s)
            elif kind == "image_body":
                content = ""
            else:
                content = merge_para_with_text(s)
            if kind == "text" and regions:
                best = max(regions, key=lambda r: overlap(r[1], s["bbox"]))
                if overlap(best[1], s["bbox"]) >= 0.5: kind = best[0]
            row = {"type": kind, "bbox": s["bbox"], "content": content}
            if kind == "title": row["level"] = get_title_level(s)
            out.append(row)
    return out


def parse(data: bytes, suffix: str) -> dict:
    """What `parse.py` does for one file (`parse_file`): the dataset for a PDF or an image, `doc_analyze_llm`,
    `pipe_ocr_mode`, then the markdown it writes (`dump_md`) and the middle JSON (`dump_middle_json`), with
    `--pred-abandon` on (its README: "Enable predicting abandon elements")."""
    m = model()
    ds = PymuDocDataset(data) if suffix.lower() == ".pdf" else ImageDataset(data)
    with _lock, tempfile.TemporaryDirectory() as images:
        inferred = ds.apply(doc_analyze_llm, MonkeyOCR_model=m, split_pages=False, pred_abandon=True)
        piped = inferred.pipe_ocr_mode(FileBasedDataWriter(images), MonkeyOCR_model=m)
        md = piped.get_markdown("images")
        middle = json.loads(piped.get_middle_json())
    page = middle["pdf_info"][0]
    found = blocks(page, abandoned(inferred, page["page_size"]))
    return {"markdown": md, "blocks": found, "page_size": page["page_size"], "middle": middle}


class Handler(BaseHTTPRequestHandler):
    """MonkeyOCR's pipeline for one page; how a page is processed is set out step by step in the adapter's
    docstring.

        GET  /health    200 once up
        GET  /served    what it serves: {weights, revision}, as each answer says
        POST /parse     {"page": base64 file, "suffix": ".pdf" or the image's}
                        -> {"markdown": the .md MonkeyOCR writes, "blocks": its blocks {type, bbox, content},
                        "page_size": [w, h], the frame of the boxes, "middle": its middle JSON, "served"}

    An error is a 500 with its message."""
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
            self._send(200, {**parse(base64.b64decode(body["page"]), body["suffix"]), "served": SERVED})
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
