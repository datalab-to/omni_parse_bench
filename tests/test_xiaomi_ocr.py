"""Vendor request, OTSL table conversion and raw completion retention, without model weights."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
from pathlib import Path

import pytest

from omni_parse_bench import harness, views
from omni_parse_bench.harness import http
from omni_parse_bench.harness.providers import xiaomi_ocr


@pytest.fixture
def server(monkeypatch):
    path = Path(harness.__file__).parent / "providers/serve/xiaomi_ocr/server.py"
    monkeypatch.syspath_prepend(str(path.parent))
    spec = importlib.util.spec_from_file_location("xiaomi_server", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_vendor_request_and_table_conversion(server, monkeypatch, tmp_path):
    from PIL import Image

    # An origin spanning two rows and two columns, plus an empty cell.
    text = ("# Title\n\n" + r"\(x^2\)" + "\n\n"
            "<fcel>A<lcel><fcel>B<nl><ucel><xcel><ecel><nl>")
    completion = {"choices": [{"message": {"content": text}, "finish_reason": "stop"}]}
    bodies = []

    class Reply:
        def raise_for_status(self): pass
        def json(self): return completion

    def post(url, json, timeout):
        bodies.append(json)
        return Reply()

    monkeypatch.setattr(server.httpx, "post", post)
    # Exercise the adapter's image encoding, server's exact settings check, vendor postprocess,
    # and the benchmark HTML reader together. The stand-in replaces only the inference request.
    def parse(config, page, timeout, body):
        raw = server.parse(base64.b64decode(body["page"]), server.settings(body))
        return {**raw, "served": config.served}

    monkeypatch.setattr(http, "parse", parse)
    config = harness.system("xiaomi_ocr")
    Image.new("RGB", (100, 150), "white").save(page := tmp_path / "page.png")
    (request,) = config.requests(frozenset({"html", "blocks"}))
    call = config.send(page, request, timeout=30)
    output, errors = config.parse(call.raw, request)
    assert not errors and set(output) == {"html"}
    assert "Title" in views.text(output["html"])
    assert '<td rowspan="2" colspan="2">A</td>' in output["html"]
    assert "<td></td>" in output["html"]
    assert "<fcel>" not in output["html"]
    assert "$ x^2 $" in call.raw["text"]
    assert call.raw["completion"] == completion
    assert call.raw["finish_reason"] == "stop"
    body = bodies[0]
    assert [part["type"] for part in body["messages"][0]["content"]] == ["text", "image_url"]
    assert body["messages"][0]["content"][0]["text"] == server.PROMPT
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert {key: body[key] for key in server.SETTINGS} == {
        "temperature": 0.0, "top_p": 0.8, "presence_penalty": 0.0,
        "repetition_penalty": 1.0, "max_tokens": 16384}
    assert hashlib.sha256(server.PROMPT.encode()).hexdigest()[:12] == request.sent["prompt_sha"]
    assert config.requests(frozenset({"blocks"})) == []


def test_empty_response_is_a_failure_and_raw_truncation_is_retained(server, monkeypatch):
    completion = {"choices": [{"message": {"content": "  "}, "finish_reason": "stop"}]}

    class Reply:
        def raise_for_status(self): pass
        def json(self): return completion

    monkeypatch.setattr(server.httpx, "post", lambda *args, **kwargs: Reply())
    settings = http.settings(xiaomi_ocr.XiaomiOcr())
    with pytest.raises(ValueError, match="empty model response"):
        server.parse(b"png", settings)
    completion["choices"][0] = {"message": {"content": "intro " + "abcd" * 3000},
                                "finish_reason": "length"}
    raw = server.parse(b"png", settings)
    assert raw["text"] == "intro abcd" and raw["finish_reason"] == "length"
    assert len(raw["completion"]["choices"][0]["message"]["content"]) > 8000


def test_padded_inline_math_is_unpadded_before_conversion():
    text = r"a $ x^2 $ and $ (k,g') $-graph, $$ y_1 $$ and $ z_{i} $."
    assert xiaomi_ocr.unpadded(text) == r"a $x^2$ and $(k,g')$-graph, $$ y_1 $$ and $z_{i}$."
    output, _ = xiaomi_ocr.parse({"text": "We have $ g_i $ here."}, None)
    assert "<em>" not in output["html"] and "$g_i$" in output["html"]


def test_vendor_postprocessing_preserves_fenced_code(server):
    text = "```text\n\n<fcel>literal<nl>\n\n```"
    assert server.finalize_document(text) == text
    with pytest.raises(ValueError, match="exactly"):
        server.settings({"settings": {"max_tokens": 5}})
