"""The vendor's page pipeline, with layout and recognition resources reused by each server worker."""
from __future__ import annotations

import importlib.metadata
import html
import json
import os
import sys
import tempfile
from importlib.resources import files
from pathlib import Path


def configuration(page: Path | None, root: Path, region_workers: int) -> dict:
    from minicpmvocr import load_config, load_prompt_map

    # Start with the SDK's own prompt map; only keep the page furniture its Markdown normally omits.
    config_path = str(files("minicpmvocr").joinpath("configs/minicpmvocr.yaml"))
    overrides = {
        "run": {"run_root": str(root), "run_tag": "page", "mode": "oneshot_file"},
        "input": {"file_path": str(page) if page else "", "files_dir": "" if page else str(root)},
        "layout": {"model_dir": os.environ["OCR_LAYOUT_MODEL_DIR"], "device": "cpu"},
        "engine": {"type": "vllm", "server_url": "http://127.0.0.1:8000",
                   "model_name": "minicpm-ocr", "max_model_len": 40960},
        "pipeline": {"max_workers": region_workers, "page_workers": 1, "render_workers": 1,
                     "overlap_layout": True, "merge_cross_page_tables": False},
        "tts": {"enabled": False},
        "upright": {"enabled": False},
    }
    cfg = load_config(config_path, overrides=overrides)
    prompt_map = load_prompt_map(cfg)
    prompt_map["markdown_assembly"]["ignore_labels"] = []
    prompt_path = root / "prompts.json"
    prompt_path.write_text(json.dumps(prompt_map), encoding="utf-8")
    overrides["prompt"] = {"prompt_map": str(prompt_path)}
    return load_config(config_path, overrides=overrides)


class Pipeline:
    """One loaded SDK detector and VLM client per uvicorn worker, as in PaddleOCR-VL's server.

    The server serializes access to each instance; the SDK overlaps layout and region recognition.
    Its public resources API keeps these objects alive across page requests.
    """

    def __init__(self):
        from minicpmvocr.backends import create_backend
        from minicpmvocr.layouts import create_layout_detector

        with tempfile.TemporaryDirectory(prefix="minicpm-startup-") as folder:
            cfg = configuration(None, Path(folder), 32)
        self.detector = create_layout_detector(cfg["layout"])
        self.engine = create_backend(cfg)
        self.detector.start()
        try:
            self.engine.start()
        except Exception:
            self.detector.stop()
            raise

    def close(self):
        self.engine.stop()
        self.detector.stop()

    def recognize(self, page: Path, root: Path, region_workers: int) -> dict:
        return recognize(page, root, region_workers,
                         resources={"detectors": [self.detector], "engine": self.engine})


def recognize(page: Path, root: Path, region_workers: int, *, resources: dict | None = None) -> dict:
    from minicpmvocr import load_prompt_map, pipelined_run
    from minicpmvocr.postprocess.markdown import assemble_markdown

    cfg = configuration(page, root, region_workers)
    prompt_map = load_prompt_map(cfg)
    summary = pipelined_run(cfg, resources=resources)
    results = sorted(Path(cfg["_meta"]["result_json_dir"]).glob("*.json"))
    if len(results) != 1:
        return {"error": f"SDK produced {len(results)} page results; expected one", "summary": summary}
    result = json.loads(results[0].read_text(encoding="utf-8"))
    # OPB reads a picture's recognized contents as alt text. Keep native Markdown unchanged, and let
    # the vendor assemble a second view with only chart/seal contents expressed as image alt text.
    html_blocks = [dict(b) for b in result["crop_blocks"]]
    for block in html_blocks:
        if block["label"] in {"chart", "seal"} and block["content"]:
            block["content"] = f'<img alt="{html.escape(block["content"], quote=True)}">'
    result["html_markdown"] = assemble_markdown(html_blocks, prompt_map)
    # Preserve partial results, failed-region statuses and raw_content as the SDK returned them.
    result["summary"] = summary
    result["vendor"] = {p: importlib.metadata.version(p)
                        for p in ("minicpm-ocr", "paddlex", "paddlepaddle", "PyMuPDF", "pypdfium2")}
    return result


if __name__ == "__main__":
    page, root, workers, output = sys.argv[1:]
    result = recognize(Path(page), Path(root), int(workers))
    Path(output).write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
