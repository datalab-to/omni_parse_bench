"""The open models' providers read real saved answers and send their options' sampling.

Each fixture in fixtures/open_weights/ is one answer from the October 2026 runs (the record's `raw`,
trimmed of fields no adapter reads), with the provider and options of the run. No adapter imports
its vendor's code (that runs on the model's server, providers/serve/), so every fixture is read here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from omni_bench_core import adapter as core
from omni_bench_core import run as runs

from omni_parse_bench import harness, views
from omni_parse_bench.harness import contract, errors

HERE = Path(__file__).parent / "fixtures" / "open_weights"
FIXTURES = sorted(HERE.glob("*.json"))


def _read(fixture: Path, outputs: frozenset[str] | None = None) -> tuple[dict, dict, dict]:
    """A fixture's answer read by its provider, for the outputs its request asked for."""
    fx = json.loads(fixture.read_text())
    api = harness.system(fx["provider"], fx["options"])
    (asked,) = api.requests(outputs or api.SUPPORTS)
    sent = fx["sent"] if fx["sent"] is not None else asked.sent
    outs, errs = api.parse(fx["raw"], contract.Request(asked.outputs, sent))
    return fx, outs, errs


@pytest.mark.parametrize("fixture", FIXTURES, ids=[p.stem for p in FIXTURES])
def test_a_saved_answer_gives_every_output_its_adapter_supports(fixture):
    fx, outs, errs = _read(fixture)
    assert errs == {}, errs
    assert views.text(outs["html"]).strip()
    if "blocks" in outs:
        assert outs["blocks"] and all(b["label"] in views.LABELS for b in outs["blocks"])


def test_every_open_weight_fixture_names_a_known_provider():
    for p in FIXTURES:
        fx = json.loads(p.read_text())
        harness.system(fx["provider"], fx["options"])


def test_a_chandra_picture_description_is_alt_text_not_page_text():
    _, outs, _ = _read(HERE / "chandra_ocr.json", frozenset({"html"}))
    described = "The seal of the National Archives"
    assert described not in views.text(outs["html"], alt=False)
    assert described in views.text(outs["html"])
    assert "CODE OF FEDERAL" in views.text(outs["html"], alt=False)


def test_a_chandra_diagram_is_alt_text_not_page_text_nor_dropped():
    from omni_parse_bench.harness.providers import chandra_ocr

    request = chandra_ocr.ChandraOcr().requests(frozenset({"html"}))[0]
    raw = {"completion": {"choices": [{"message": {"content": "..."}, "finish_reason": "stop"}]},
           "blocks": [{"label": "Text", "raw": "Intro", "html": "<p>Intro</p>"},
                      {"label": "Diagram", "raw": "<p>Model Series</p>", "html": "<p>Model Series</p>"}]}
    outs, _ = chandra_ocr.parse(raw, request)
    assert "Model Series" in views.text(outs["html"])
    assert "Model Series" not in views.text(outs["html"], alt=False)


def test_a_hunyuan_chart_is_alt_text_not_page_text():
    from omni_parse_bench.harness.providers import hunyuan

    said = json.dumps([
        {"layout_type": "paragraph", "bbox": "(0,0),(9,0),(9,9),(0,9)", "text": "Sales by year"},
        {"layout_type": "chart", "bbox": "(0,10),(9,10),(9,90),(0,90)", "text": "| 2024 | 12 |"}])
    page = hunyuan.page_text(said)
    assert "Sales by year" in page and "<img alt=" in page
    assert "12" not in views.text(page, alt=False)


def test_an_unknown_label_fails_the_blocks_only():
    from omni_parse_bench.harness.providers import unlimited

    reply = ("<|det|>text [0, 0, 500, 100]<|/det|>Kept\n"
             "<|det|>no_such_label [0, 100, 500, 200]<|/det|>Also kept")
    request = unlimited.UnlimitedOcr().requests(frozenset({"html", "blocks"}))[0]
    raw = {"completion": {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]}}
    outs, errs = unlimited.parse(raw, request)
    assert "Also kept" in views.text(outs["html"]) and "blocks" in errs and "blocks" not in outs


def test_an_open_models_malformed_block_or_unknown_label_fails_the_blocks_only():
    """A block with no box, or a type LABELS lacks, fails the blocks output only; the html is still graded."""
    from omni_parse_bench.harness.providers import dots, mineru

    request = mineru.MinerU().requests(frozenset({"html", "blocks"}))[0]
    raw = {"markdown": "Kept", "blocks": [{"type": "no_such_label", "bbox": [0, 0, 1, 1], "content": "Kept"}]}
    for blocks in (raw["blocks"], [{"type": "text", "content": "no box"}], ["not an object"]):
        outs, errs = mineru.parse(raw | {"blocks": blocks}, request)
        assert "Kept" in views.text(outs["html"]) and "blocks" in errs and "blocks" not in outs, blocks
    request = dots.Dots().requests(frozenset({"html", "blocks"}))[0]
    raw = {"markdown": "Kept", "image_size": [100, 100],
           "cells": [{"category": "Text", "bbox": [0, 0, 50], "text": "Kept"}]}
    outs, errs = dots.parse(raw, request)
    assert "Kept" in views.text(outs["html"]) and "blocks" in errs and "blocks" not in outs
    with pytest.raises(KeyError):
        mineru.parse({"markdown": "Kept"}, request._replace(outputs=frozenset({"blocks"})))


def test_an_api_vendors_malformed_blocks_fail_the_blocks_only():
    request = harness.system("datalab").requests(frozenset({"html", "blocks"}))[0]
    raw = {"html": "<p>Kept</p>", "chunks": {"page_info": {"0": {"bbox": [0, 0, 10, 10]}},
                                           "blocks": [{"block_type": "Text", "bbox": [0, 0, 5], "page": 0}]}}
    outs, errs = harness.system("datalab").parse(raw, request)
    assert outs["html"] == "<p>Kept</p>" and "blocks" in errs and "blocks" not in outs


def test_an_infinity_reply_cut_at_the_token_limit_keeps_its_complete_elements():
    """The server reads a cut reply up to its last complete element, as the SDK does; the adapter keeps it."""
    from omni_parse_bench.harness.providers import infinity

    request = infinity.Infinity().requests(frozenset({"html", "blocks"}))[0]
    raw = {"completion": {"choices": [{"message": {"content": "..."}, "finish_reason": "length"}]},
           "json": '[{"bbox": [0, 0, 500, 100], "category": "text", "text": "Whole"}]', "markdown": "Whole"}
    outs, errs = infinity.parse(raw, request)
    assert "Whole" in views.text(outs["html"]) and len(outs["blocks"]) == 1


def test_a_reply_cut_at_the_token_limit_is_read_as_it_is():
    """As the vendor's own client reads it; a reply that stopped for another reason fails."""
    from omni_parse_bench.harness.providers import nanonets

    request = nanonets.Nanonets().requests(frozenset({"html"}))[0]
    cut = {"choices": [{"message": {"content": "text"}, "finish_reason": "length"}]}
    assert "text" in nanonets.parse(cut, request)[0]["html"]
    with pytest.raises(errors.SystemFailed):
        nanonets.parse({"choices": [{"message": {"content": "text"}, "finish_reason": "abort"}]}, request)


def test_a_model_without_layout_is_never_asked_for_blocks(tmp_path, monkeypatch):
    """Nanonets reads html only, so a page that wants blocks too is asked for html alone."""
    from omni_parse_bench.harness import http
    from omni_parse_bench.harness.providers import llm

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(llm, "image", lambda *a: b"png")
    served = {"weights": "org/model", "revision": "main"}
    monkeypatch.setattr(http, "served", lambda *a: ("org/model@main", served))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: {"choices": [{"message": {"content": "# Title"},
                                                                   "finish_reason": "stop"}]})
    record = core.predict(harness.system("nanonets-ocr"), harness.Input(pdf, frozenset({"html", "blocks"})))
    [page] = record["output"]["pages"]
    assert list(page) == ["html"] and "Title" in views.text(page["html"])


def folder(provider: str, **options) -> str:
    """The run folder's name of `provider` at `options`, on one question."""
    return runs.stem(harness.system(provider, options), {"dataset": "d", "task": "parse"})


def test_an_llm_run_is_named_after_its_model():
    name = folder("openai/gpt-5.6-sol")
    assert name.startswith("openai__gpt-5.6-sol-") and name != folder("openai/gpt-5.5")


def _adapter(mod):
    """The adapter class a provider module defines."""
    return next(v for v in vars(mod).values()
                if isinstance(v, type) and issubclass(v, harness.Parser)
                and v.__module__ == mod.__name__)


def _changed(config):
    """`config` with every number among its settings changed."""
    import dataclasses

    new = {f.name: getattr(config, f.name) * 2 + (0.5 if f.type == "float" else 1)
           for f in dataclasses.fields(config) if f.type in ("int", "float")}
    return dataclasses.replace(config, **new)


@pytest.mark.parametrize("name", ["chandra_ocr", "deepseek_ocr", "dots", "hunyuan", "infinity", "lighton",
                                  "olmocr", "paddleocr_vl", "surya_ocr", "unlimited"])
def test_a_server_gets_every_setting_from_the_config(name, tmp_path, monkeypatch):
    """The server holds no setting of its own: the adapter sends its options, so an option changes it,
    and the request records it, so the run is named for it."""
    import importlib

    from PIL import Image

    from omni_parse_bench.harness import http

    mod = importlib.import_module(f"omni_parse_bench.harness.providers.{name}")
    config = _changed(_adapter(mod)())
    got = {}
    answer = {"completion": {}, "served": {"weights": "org/model", "revision": "main"}}
    monkeypatch.setattr(http, "post", lambda url, body, *a, **k: got.update(body) or answer)
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    mod.call(page, mod.requests(mod.SUPPORTS, config)[0], config=config)
    default = http.settings(_adapter(mod)(), "long_edge")
    assert got["settings"] == http.settings(config, "long_edge") != default
    assert mod.requests(mod.SUPPORTS, config)[0].sent["settings"] == http.settings(config)


def test_nanonets_asks_vllm_with_its_config(tmp_path, monkeypatch):
    from PIL import Image

    from omni_parse_bench.harness.providers import llm, nanonets

    from omni_parse_bench.harness import http

    config = _changed(nanonets.Nanonets())
    got = {}
    served = {"weights": "org/model", "revision": "main"}
    monkeypatch.setattr(http, "served", lambda *a: ("org/model@main", served))
    monkeypatch.setattr(llm, "chat", lambda url, body, *a, **k: got.update(body) or {})
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    call = nanonets.call(page, nanonets.requests(frozenset({"html"}), config)[0], config=config)
    # vLLM serves the weights under <weights>@<revision>: the request names it, and the answer records it
    assert got["model"] == "org/model@main" and call.raw["served"] == served
    assert (got["temperature"], got["top_p"], got["max_tokens"]) == (config.temperature, config.top_p,
                                                                      config.max_tokens)
    assert got["extra_body"] == {"repetition_penalty": config.repetition_penalty}


@pytest.mark.parametrize("provider", ["chandra-ocr", "deepseek-ocr", "dots-mocr", "glm-ocr", "hunyuan-ocr",
                                      "infinity-parser2", "lightonocr", "mineru", "nanonets-ocr", "olmocr",
                                      "paddleocr-vl", "surya-ocr", "unlimited-ocr"])
def test_a_served_model_run_is_named_by_every_option(provider):
    """Every option names the run, the server's address included: a new address is a new run folder."""
    a = folder(provider)
    assert folder(provider, base_url="https://one.example") != a
    if "max_tokens" in harness.system(provider).options(): assert folder(provider, max_tokens=7) != a


@pytest.mark.parametrize("provider", ["chandra-ocr", "nanonets-ocr"])
def test_a_server_that_refuses_the_connection_stops_the_run(provider, tmp_path):
    """Nothing listening at base_url is the same for every page: the run stops and says how to start the
    server, instead of recording each page as a failure."""
    import socket

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]   # Note: closed on leaving, so nothing listens there.
    from PIL import Image

    Image.new("RGB", (64, 64), "white").save(pdf := tmp_path / "p.png")
    api = harness.system(provider, {"base_url": f"http://127.0.0.1:{port}"})
    with pytest.raises(Exception) as e:      # the connection error itself, with a note saying how to start it
        core.predict(api, harness.Input(pdf, frozenset({"html"})))
    note = "\n".join(getattr(e.value, "__notes__", []))
    assert f"no server at http://127.0.0.1:{port}" in note and f"providers/serve/{api.SERVE}" in note, note
    assert provider in note, note


def test_every_served_model_says_where_its_server_is():
    for name in harness.PROVIDERS:
        c = harness.adapter_class(name)
        if getattr(c(), "base_url", "").startswith("http://127.0.0.1"):
            serve = Path(harness.__file__).parent / "providers" / "serve"
            assert c.SERVE and (serve / c.SERVE).is_dir(), name
            assert not c.keys and "OPB_ENDPOINT_KEY" in c.ENV


def test_a_server_reply_must_say_what_it_serves(tmp_path, monkeypatch):
    """What answered is what the server says it serves; a server that doesn't say is out of date, which stops
    the run rather than failing the page."""
    from omni_parse_bench.harness import http
    from omni_parse_bench.harness.providers import chandra_ocr

    (page := tmp_path / "p.png").write_bytes(b"png")
    config = chandra_ocr.ChandraOcr()
    monkeypatch.setattr(http, "post", lambda *a, **k: {"completion": {}})
    with pytest.raises(ValueError, match="doesn't say what it serves"):
        http.parse(config, page, 10)
    served = {"weights": "org/model", "revision": "main"}
    monkeypatch.setattr(http, "post", lambda *a, **k: {"served": served})
    assert http.parse(config, page, 10)["served"]["weights"] == "org/model"


def test_vllm_is_asked_what_it_serves_with_the_endpoint_key(monkeypatch):
    """A model with no server.py says what it serves through vLLM's /v1/models, which needs the endpoint key
    when one is set; a refusal is a failed call with its status, not a page that reads wrong."""
    import httpx

    from omni_parse_bench.harness import budget, errors, http

    seen = {}

    def get(url, timeout, headers):
        seen.update(headers)
        status = 200 if headers.get("Authorization") == "Bearer k" else 401
        return httpx.Response(status, json={"data": [{"id": "org/model@main"}]},
                              request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx, "get", get)
    monkeypatch.setenv("OPB_ENDPOINT_KEY", "k")
    said = http.served("http://x", budget.Budget(10))
    assert said == ("org/model@main", {"weights": "org/model", "revision": "main"})
    monkeypatch.setenv("OPB_ENDPOINT_KEY", "wrong")
    with pytest.raises(errors.SystemFailed) as got:
        http.served("http://x", budget.Budget(10))
    assert got.value.status == 401
