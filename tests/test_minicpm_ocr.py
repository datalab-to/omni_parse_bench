"""MiniCPM's SDK result contract, using synthetic responses (no live model response is claimed)."""
from __future__ import annotations

import copy
import importlib.util
import os
import shlex
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from omni_parse_bench import harness, views
from omni_parse_bench.harness import errors, http
from omni_parse_bench.harness.providers import minicpm_ocr as model

SERVE = Path(model.__file__).parent / "serve" / "minicpm-ocr"


def test_start_script_exposes_the_vllm_build_tools_to_runtime_subprocesses(tmp_path):
    """FlashInfer finds ninja installed in vLLM's venv, even with a minimal inherited PATH."""
    vllm_env, sdk_env, tools = (tmp_path / p for p in ("vllm", "sdk", "tools"))
    for p in (vllm_env / "bin", sdk_env / "bin", tools): p.mkdir(parents=True)

    def executable(path, body):
        path.write_text("#!/bin/sh\nset -e\n" + body)
        path.chmod(0o755)

    executable(vllm_env / "bin/python", f"printf '%s\\n' {shlex.quote(str(tmp_path / 'cuda'))}\n")
    executable(vllm_env / "bin/ninja", "exit 0\n")
    executable(vllm_env / "bin/vllm", 'command -v ninja > "$NINJA_PROBE"\n')
    executable(sdk_env / "bin/uvicorn", "exit 0\n")
    executable(tools / "curl", "exit 0\n")
    script = (SERVE / "start.sh").read_text().replace("/opt/minicpm/.venv-vllm", str(vllm_env))
    script = script.replace("/opt/sdk", str(sdk_env))
    # macOS's bundled Bash lacks wait -n; both short-lived stand-ins finish in this test.
    script = script.replace('wait -n "$VLLM" "$SERVER"', 'wait "$VLLM" "$SERVER"')
    env = dict(os.environ, PATH=f"{tools}:/usr/bin:/bin", NINJA_PROBE=str(tmp_path / "probe"))
    subprocess.run(["/bin/bash", "-c", script], env=env, check=True, timeout=5)
    assert (tmp_path / "probe").read_text().strip() == str(vllm_env / "bin/ninja")


@pytest.fixture
def answer():
    table = '<table><tr><th>Year</th><th>Sales</th></tr><tr><td>2025</td><td>12</td></tr></table>'
    text = '# Results\n\n' + table + '\n\n$$E=mc^2$$\n\nPage 1'
    return {"markdown": text, "html_markdown": text, "image_width": 200, "image_height": 400,
            "crop_blocks": [
                {"label": "footer", "order": 3, "bbox": [0, 380, 200, 400], "content": "Page 1"},
                {"label": "doc_title", "order": 0, "bbox": [0, 0, 200, 40], "content": "Results"},
                {"label": "table", "order": 1, "bbox": [0, 40, 200, 200], "content": table},
                {"label": "display_formula", "order": 2, "bbox": [0, 200, 200, 240], "content": "E=mc^2"}],
            "served": {"weights": model.WEIGHTS, "revision": model.REVISION}}


def test_registered_pipeline_keeps_markdown_tables_math_furniture_and_real_layout(answer):
    system = harness.system("minicpm-ocr")
    before = copy.deepcopy(answer)
    (request,) = system.requests(model.SUPPORTS)
    out, errs = system.parse(answer, request)
    assert not errs and set(out) == model.SUPPORTS
    assert out["markdown"] == answer["markdown"] and answer == before
    assert "<table>" in out["html"] and "E=mc^2" in out["html"]
    assert "Page 1" in views.text(out["html"])
    assert [b["label"] for b in out["blocks"]] == ["heading", "table", "equation", "page_furniture"]
    assert out["blocks"][1]["bbox"] == [0, 0.1, 1, 0.5]
    assert "2025" in out["blocks"][1]["text"] and "<td>" not in out["blocks"][1]["text"]


def test_native_markdown_and_html_picture_contents_are_separate(answer):
    answer["markdown"] = "Chart data: 321"
    answer["html_markdown"] = '<img alt="Chart data: 321">'
    out, _ = model.parse(answer, harness.system("minicpm-ocr").requests(model.SUPPORTS)[0])
    assert out["markdown"] == "Chart data: 321"
    assert "321" in views.text(out["html"]) and "321" not in views.text(out["html"], alt=False)


@pytest.mark.parametrize("broken", [
    {"crop_blocks": [{"label": "unknown", "order": 0, "bbox": [0, 0, 1, 1], "content": "kept"}]},
    {"crop_blocks": [{"label": "text", "order": 0, "content": "missing box"}]},
    {"crop_blocks": [{"label": "text", "order": 0, "bbox": [0, 0, 1], "content": "bad box"}]},
    {"image_width": 0},
])
def test_malformed_layout_fails_blocks_only(answer, broken):
    out, errs = model.parse(answer | broken, model.MiniCpmOcr().requests(model.SUPPORTS)[0])
    assert out["markdown"] == answer["markdown"] and "Results" in out["html"]
    assert "blocks" not in out and "blocks" in errs


def test_blank_page_is_valid_but_no_sdk_page_is_a_failure(answer):
    blank = answer | {"markdown": "", "html_markdown": "", "crop_blocks": []}
    request = model.MiniCpmOcr().requests(model.SUPPORTS)[0]
    out, errs = model.parse(blank, request)
    assert out == {"html": "", "markdown": "", "blocks": []} and not errs
    with pytest.raises(errors.SystemFailed, match="expected one"):
        model.parse({"error": "SDK produced 0 page results; expected one"}, request)


def test_partial_recognition_is_kept_as_the_sdk_returns_it(answer):
    answer["crop_blocks"][0].update(status="vllm_error", raw_content="", content="")
    answer["summary"] = {"num_failed_blocks": 1}
    out, errs = model.parse(answer, model.MiniCpmOcr().requests(model.SUPPORTS)[0])
    assert not errs and "Results" in out["html"]
    assert answer["crop_blocks"][0]["status"] == "vllm_error"


def test_send_passes_page_budget_and_options_to_server(tmp_path, monkeypatch, answer):
    page = tmp_path / "page.png"
    page.write_bytes(b"synthetic")
    got = {}
    monkeypatch.setattr(http, "post", lambda url, body, *a, **kw: got.update(body) or answer)
    system = model.MiniCpmOcr(region_workers=7)
    request = system.requests(model.SUPPORTS)[0]
    assert system.send(page, request, timeout=12).raw == answer
    assert got["settings"] == request.sent["settings"] == {"region_workers": 7}
    assert "timeout" not in got and got["suffix"] == ".png"
    assert system.requests(frozenset()) == []


@pytest.mark.parametrize("value", [0, -1, True, 1.5])
def test_invalid_region_workers_are_refused(value):
    with pytest.raises(ValueError, match="region_workers"):
        model.MiniCpmOcr(region_workers=value)


def load_server_file(name):
    spec = importlib.util.spec_from_file_location(f"minicpm_{name}", SERVE / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_server_reuses_one_pipeline_and_preserves_its_raw_result(monkeypatch, answer):
    pytest.importorskip("fastapi")
    server = load_server_file("server")
    observed = []

    class Pipeline:
        def recognize(self, source, root, workers):
            assert source.read_bytes() == b"synthetic" and workers == 3
            observed.append((id(self), root))
            return answer

    monkeypatch.setattr(server, "_pipeline", Pipeline())
    monkeypatch.setattr(server, "KEY", "key")
    page = server.Page(page="c3ludGhldGlj", suffix=".png", settings={"region_workers": 3})
    with pytest.raises(server.HTTPException) as got:
        server.parse(page)
    assert got.value.status_code == 401
    out = server.parse(page, authorization="Bearer key")
    assert out["crop_blocks"] == answer["crop_blocks"]
    assert server.parse(page, authorization="Bearer key") == out
    assert len(observed) == 2 and observed[0][0] == observed[1][0]
    assert observed[0][1] != observed[1][1] and all(not root.exists() for _, root in observed)

    def failure(*args, **kwargs):
        raise RuntimeError("SDK failed")

    monkeypatch.setattr(server._pipeline, "recognize", failure)
    with pytest.raises(server.HTTPException) as got:
        server.parse(page, authorization="Bearer key")
    assert got.value.status_code == 500 and "SDK failed" in got.value.detail


def test_server_serializes_access_to_each_loaded_paddle_detector(monkeypatch, answer):
    pytest.importorskip("fastapi")
    server = load_server_file("server")
    barrier = threading.Barrier(2)
    active, peak = 0, 0

    class Pipeline:
        def recognize(self, *args):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            time.sleep(0.02)
            active -= 1
            return answer

    monkeypatch.setattr(server, "_pipeline", Pipeline())
    monkeypatch.setattr(server, "KEY", None)
    page = server.Page(page="c3ludGhldGlj", suffix=".png", settings={"region_workers": 3})

    def request():
        barrier.wait(timeout=5)
        return server.parse(page)

    with ThreadPoolExecutor(max_workers=2) as callers:
        a, b = callers.submit(request), callers.submit(request)
        assert a.result()["crop_blocks"] == b.result()["crop_blocks"] == answer["crop_blocks"]
    assert peak == 1


@pytest.mark.parametrize("persistent", [False, True])
def test_worker_runs_the_real_sdk_pipeline_with_standin_models(tmp_path, monkeypatch, persistent):
    """Optional SDK integration: real loading, cropping orchestration, table conversion and assembly.

    Run with the pinned SDK source installed; no Paddle, GPU, model weights or network are used.
    """
    pytest.importorskip("minicpmvocr")
    import numpy as np
    from minicpmvocr.pipeline import overlapped
    from minicpmvocr import backends, layouts
    from PIL import Image

    worker = load_server_file("worker")
    layout_dir = tmp_path / "layout"
    layout_dir.mkdir()
    (layout_dir / "inference.pdiparams").touch()
    (layout_dir / "inference.yml").write_text("Global:\n  model_name: PP-DocLayoutV3\n")
    monkeypatch.setenv("OCR_LAYOUT_MODEL_DIR", str(layout_dir))
    seen = {}
    created = {"detector": 0, "engine": 0}
    stopped = {"detector": 0, "engine": 0}

    class Detector:
        def start(self): pass
        def stop(self): stopped["detector"] += 1

        def detect(self, images):
            return [[{"label": label, "class_id": i, "score": 1.0, "bbox": [0, i * 40, 200, i * 40 + 40]}
                     for i, label in enumerate(("header", "table", "chart", "footer"))]]

        def crop(self, image, detections):
            return [d | {"image": np.asarray(image)[d["bbox"][1]:d["bbox"][3], :]} for d in detections]

    class Engine:
        name = "standin"
        def start(self): pass
        def stop(self): stopped["engine"] += 1

        def recognize(self, image, *, prompt, **kwargs):
            text = ("Page furniture" if prompt == "Text Recognition:"
                    else '<table><tr><td>123</td></tr></table>')
            return {"text": text, "output_token_count": 3}

    def detector(cfg):
        created["detector"] += 1
        seen["device"] = cfg["device"]
        return Detector()

    def engine(cfg):
        created["engine"] += 1
        seen["workers"] = cfg["pipeline"]["max_workers"]
        seen["tts"] = cfg["tts"]["enabled"]
        return Engine()

    monkeypatch.setattr(overlapped, "create_layout_detector", detector)
    monkeypatch.setattr(overlapped, "create_backend", engine)
    monkeypatch.setattr(layouts, "create_layout_detector", detector)
    monkeypatch.setattr(backends, "create_backend", engine)
    monkeypatch.setattr(worker.importlib.metadata, "version", lambda name: "standin")
    Image.new("RGB", (200, 400), "white").save(page := tmp_path / "page.png")
    if persistent:
        pipeline = worker.Pipeline()
        raw = pipeline.recognize(page, tmp_path, 2)
        other = tmp_path / "second"
        other.mkdir()
        again = pipeline.recognize(page, other, 2)
        assert again["markdown"] == raw["markdown"]
        assert again["crop_blocks"] == raw["crop_blocks"]
        assert created == {"detector": 1, "engine": 1}
        assert stopped == {"detector": 0, "engine": 0}
        pipeline.close()
        assert stopped == {"detector": 1, "engine": 1}
    else:
        raw = worker.recognize(page, tmp_path, 2)
    assert "error" not in raw, raw
    assert seen == {"device": "cpu", "workers": 32 if persistent else 2, "tts": False}
    assert [b["label"] for b in raw["crop_blocks"]] == ["header", "table", "chart", "footer"]
    assert raw["markdown"].count("Page furniture") == 2
    assert raw["markdown"].count("<table>") == 2  # native chart output is untouched
    outputs, errs = model.parse(raw, model.MiniCpmOcr().requests(model.SUPPORTS)[0])
    assert not errs and outputs["html"].count("<table>") == 1
    assert '<img alt=' in outputs["html"]
