"""OXR's API contract, using synthetic answers (no live model answer is claimed)."""
from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path

import httpx
import pytest

from omni_parse_bench import harness, views
from omni_parse_bench.harness.providers import oxr as model

SERVE = Path(model.__file__).parent / "serve" / "oxr"


@pytest.fixture
def answer():
    table = "<table><tr><th>Year</th><th>Sales</th></tr><tr><td>2025</td><td>12</td></tr></table>"
    blocks = [
        {"idx": 0, "type": "Title", "bbox": [0, 0, 200, 40], "content": "Results", "format": "text"},
        {"idx": 1, "type": "Table", "bbox": [0, 40, 200, 200], "content": table, "format": "html"},
        {"idx": 2, "type": "Formula", "bbox": [0, 200, 200, 240], "content": "E=mc^2", "format": "latex"},
        {"idx": 3, "type": "Page-footer", "bbox": [0, 380, 200, 400], "content": "Page 1", "format": "text"}]
    md = f"# Results\n\n{table}\n\n$$E=mc^2$$\n\nPage 1"
    return {"outputs": {"markdown": md, "json": {"pages": [
                {"page_num": 0, "page_size": {"w": 200, "h": 400}, "blocks": blocks}]}},
            "metadata": {"page_num": 1}, "served": {"weights": model.WEIGHTS, "revision": model.REVISION}}


def test_registered_adapter_keeps_markdown_tables_math_furniture_and_layout(answer):
    system = harness.system("oxr")
    before = copy.deepcopy(answer)
    (request,) = system.requests(model.SUPPORTS)
    out, errs = system.parse(answer, request)
    assert not errs and set(out) == model.SUPPORTS and answer == before
    assert out["markdown"] == answer["outputs"]["markdown"]
    assert "<table>" in out["html"] and "E=mc^2" in out["html"] and "Page 1" in views.text(out["html"])
    assert [b["label"] for b in out["blocks"]] == ["heading", "table", "equation", "page_furniture"]
    assert out["blocks"][1]["bbox"] == [0, 0.1, 1, 0.5]
    assert "2025" in out["blocks"][1]["text"] and "<td>" not in out["blocks"][1]["text"]


def test_an_unknown_block_type_fails_blocks_only(answer):
    answer["outputs"]["json"]["pages"][0]["blocks"][0]["type"] = "Sidebar"
    out, errs = model.parse(answer, model.requests(model.SUPPORTS)[0])
    assert "blocks" in errs and "Sidebar" in errs["blocks"] and {"html", "markdown"} <= set(out)


@pytest.fixture
def server(monkeypatch):
    spec = importlib.util.spec_from_file_location("oxr_server", SERVE / "server.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_server_asks_for_furniture_and_maps_the_api_codes(server, monkeypatch):
    sent, replies = [], iter([
        {"code": 0, "warnings": [], "data": {"result": {"outputs": {"markdown": "x"}}, "metadata": {}}},
        {"code": 1137, "message": "model timed out", "data": None},
        {"code": 1133, "message": "bad parameter", "data": None}])

    def post(url, *, data, files, timeout):
        sent.append((data, files))
        return httpx.Response(200, json=next(replies))

    monkeypatch.setattr(server.httpx, "post", post)
    ok = {"outputs": {"markdown": "x"}, "metadata": {}, "warnings": []}
    assert server.parse(b"%PDF", ".pdf") == (200, ok)
    assert server.parse(b"%PDF", ".pdf")[0] == 500
    assert server.parse(b"%PDF", ".pdf")[0] == 400
    data, files = sent[0]
    assert json.loads(data["feature_config"]) == {"keep_header_footer": True}
    assert data["output_formats"] == ["markdown", "json"] and files["file"][0] == "input.pdf"
