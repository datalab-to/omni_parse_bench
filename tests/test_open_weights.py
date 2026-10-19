"""The open models' providers read real saved answers and send their Config's sampling.

Each fixture in fixtures/open_weights/ is one answer from the October 2026 runs (the record's `raw`,
trimmed of fields no adapter reads), with the provider and options of the run. No adapter imports
its vendor's code (that runs on the model's server, providers/serve/), so every fixture is read here.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from omni_parse_bench import views
from omni_parse_bench.harness import contract, errors, registry

HERE = Path(__file__).parent / "fixtures" / "open_weights"
FIXTURES = sorted(HERE.glob("*.json"))


def _read(fixture: Path, outputs: frozenset[str] | None = None) -> tuple[dict, dict, dict]:
    """A fixture's answer read by its provider, for the outputs its request asked for."""
    fx = json.loads(fixture.read_text())
    api = registry.adapter(fx["provider"])
    config = registry.config_for(fx["provider"], fx["options"])
    (asked,) = api.requests(outputs or api.SUPPORTS, config)
    sent = fx["sent"] if fx["sent"] is not None else asked.sent
    outs, errs = api.parse(fx["raw"], contract.Request(asked.outputs, sent), config)
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
        registry.config_for(fx["provider"], fx["options"])


def test_a_chandra_picture_description_is_alt_text_not_page_text():
    _, outs, _ = _read(HERE / "chandra_ocr.json", frozenset({"html"}))
    described = "The seal of the National Archives"
    assert described not in views.text(outs["html"], alt=False)
    assert described in views.text(outs["html"])
    assert "CODE OF FEDERAL" in views.text(outs["html"], alt=False)


def test_a_chandra_diagram_is_alt_text_not_page_text_nor_dropped():
    from omni_parse_bench.harness.providers import chandra_ocr

    request = chandra_ocr.requests(frozenset({"html"}), chandra_ocr.Config())[0]
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
    request = unlimited.requests(frozenset({"html", "blocks"}), unlimited.Config())[0]
    raw = {"completion": {"choices": [{"message": {"content": reply}, "finish_reason": "stop"}]}}
    outs, errs = unlimited.parse(raw, request)
    assert "Also kept" in views.text(outs["html"]) and "blocks" in errs and "blocks" not in outs


def test_an_infinity_reply_cut_at_the_token_limit_keeps_its_complete_elements():
    """The server reads a cut reply up to its last complete element, as the SDK does; the adapter keeps it."""
    from omni_parse_bench.harness.providers import infinity

    request = infinity.requests(frozenset({"html", "blocks"}), infinity.Config())[0]
    raw = {"completion": {"choices": [{"message": {"content": "..."}, "finish_reason": "length"}]},
           "json": '[{"bbox": [0, 0, 500, 100], "category": "text", "text": "Whole"}]', "markdown": "Whole"}
    outs, errs = infinity.parse(raw, request)
    assert "Whole" in views.text(outs["html"]) and len(outs["blocks"]) == 1


def test_a_reply_cut_at_the_token_limit_is_read_as_it_is():
    """As the vendor's own client reads it; a reply that stopped for another reason fails."""
    from omni_parse_bench.harness.providers import nanonets

    request = nanonets.requests(frozenset({"html"}), nanonets.Config())[0]
    cut = {"choices": [{"message": {"content": "text"}, "finish_reason": "length"}]}
    assert "text" in nanonets.parse(cut, request)[0]["html"]
    with pytest.raises(errors.VendorError):
        nanonets.parse({"choices": [{"message": {"content": "text"}, "finish_reason": "abort"}]}, request)


def test_a_model_without_layout_has_its_blocks_recorded_unsupported(tmp_path, monkeypatch):
    """Nanonets reads html only, so a run that wants blocks records them unsupported, not failed."""
    from omni_parse_bench.harness import page
    from omni_parse_bench.harness.providers import llm

    (pdf := tmp_path / "p.pdf").write_bytes(b"%PDF")
    monkeypatch.setattr(llm, "image", lambda *a: b"png")
    monkeypatch.setattr(llm, "chat", lambda *a, **k: {"choices": [{"message": {"content": "# Title"},
                                                                   "finish_reason": "stop"}]})
    record = page.predict("nanonets-ocr", pdf, {"html", "blocks"})
    assert record["errors"] == {"blocks": "unsupported"} and "Title" in views.text(record["outputs"]["html"])


def test_the_published_llm_run_names_are_unchanged():
    # Note: the published runs' names; a field added to llm.Config would change them.
    assert registry.out_name("openai/gpt-5.6-sol") == "openai__gpt-5.6-sol-86e872e5"




def _changed(config):
    """`config` with every number among its settings changed."""
    import dataclasses

    new = {f.name: getattr(config, f.name) * 2 + (0.5 if f.type == "float" else 1)
           for f in dataclasses.fields(config) if f.type in ("int", "float")}
    return dataclasses.replace(config, **new)


@pytest.mark.parametrize("name", ["chandra_ocr", "deepseek_ocr", "dots", "hunyuan", "infinity", "lighton",
                                  "olmocr", "paddleocr_vl", "surya_ocr", "unlimited"])
def test_a_server_gets_every_setting_from_the_config(name, tmp_path, monkeypatch):
    """The server holds no setting of its own: the adapter sends its Config's, so an option changes it,
    and the request records it, so the run is named for it."""
    import importlib

    from PIL import Image

    from omni_parse_bench.harness import http

    mod = importlib.import_module(f"omni_parse_bench.harness.providers.{name}")
    config = _changed(mod.Config())
    got = {}
    answer = {"completion": {}, "model": getattr(config, "model", None)}
    monkeypatch.setattr(http, "post", lambda url, body, *a, **k: got.update(body) or answer)
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    mod.call(page, mod.requests(mod.SUPPORTS, config)[0], config=config)
    assert got["settings"] == http.settings(config, "long_edge") != http.settings(mod.Config(), "long_edge")
    assert mod.requests(mod.SUPPORTS, config)[0].sent["settings"] == http.settings(config)


def test_nanonets_asks_vllm_with_its_config(tmp_path, monkeypatch):
    from PIL import Image

    from omni_parse_bench.harness.providers import llm, nanonets

    config = _changed(nanonets.Config())
    got = {}
    monkeypatch.setattr(llm, "chat", lambda url, body, *a, **k: got.update(body) or {})
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    nanonets.call(page, nanonets.requests(frozenset({"html"}), config)[0], config=config)
    assert (got["temperature"], got["top_p"], got["max_tokens"]) == (config.temperature, config.top_p,
                                                                      config.max_tokens)
    assert got["extra_body"] == {"repetition_penalty": config.repetition_penalty}


@pytest.mark.parametrize("provider", ["chandra-ocr", "deepseek-ocr", "dots-mocr", "glm-ocr", "hunyuan-ocr",
                                      "infinity-parser2", "lightonocr", "mineru", "nanonets-ocr", "olmocr",
                                      "paddleocr-vl", "surya-ocr", "unlimited-ocr"])
def test_a_served_model_run_is_named_without_its_server_address(provider):
    """A server's address is new each time it starts, so a resumed run keeps its name; a setting still
    names its own run."""
    a = registry.out_name(provider, {"base_url": "https://one.example"})
    b = registry.out_name(provider, {"base_url": "https://two.example"})
    assert a == b == registry.out_name(provider)
    knob = "max_tokens" if "max_tokens" in registry.settings_for(provider) else None
    if knob: assert registry.out_name(provider, {knob: 7}) != a
