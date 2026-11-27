"""PP-StructureV3's adapter: its label table covers every label of its layout model, its boxes go back onto
the page as sent, and a block it cannot place fails the blocks, never guessed."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from omni_parse_bench import views
from omni_parse_bench.harness import contract
from omni_parse_bench.harness.providers import pp_structurev3 as pp

FIXTURE = Path(__file__).parent / "fixtures" / "open_weights" / "pp_structurev3.json"
# PP-DocLayout_plus-L's label_list, as its inference.yml has it.
MODEL_LABELS = (
    "paragraph_title image text number abstract content figure_title formula table reference doc_title "
    "footnote vision_footnote header algorithm footer seal chart formula_number aside_text "
    "reference_content").split()


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())["raw"]


def _parse(raw: dict, outputs=frozenset({"html", "blocks"}), **options):
    config = pp.PpStructureV3(**options)
    (asked,) = config.requests(outputs)
    return config.parse(raw, contract.Request(asked.outputs, asked.sent))


def test_every_label_of_the_layout_model_maps_to_a_view_label():
    assert set(pp.LABELS) == set(MODEL_LABELS)
    assert set(pp.LABELS.values()) <= set(views.LABELS)


def test_html_is_the_markdown_and_blocks_are_the_pipelines_blocks():
    raw = _raw()
    outs, errs = _parse(raw)
    assert errs == {}
    assert views.text(outs["html"]).strip()
    found = raw["parsing_res_list"]
    assert [b["label"] for b in outs["blocks"]] == [pp.LABELS[b["block_label"]] for b in found]
    assert all(0 <= x <= 1 for b in outs["blocks"] for x in b["bbox"])
    assert not any("<" in b["text"] for b in outs["blocks"])


def _one(angle, box=(102, 93, 320, 116), size=(1224, 1584)):
    raw = {"markdown": "x", "width": size[0], "height": size[1], "angle": angle,
           "parsing_res_list": [{"block_label": "header", "block_bbox": list(box),
                                "block_content": "AUTOPSY"}]}
    return _parse(raw, frozenset({"blocks"}))[0]["blocks"][0]["bbox"]


def test_a_page_the_pipeline_turned_upright_has_its_boxes_turned_back_onto_the_page_as_sent():
    # An A4-like page shot sideways: the classifier said 270, the upright header at the top left is the page
    # as sent's bottom left (checked against the rendered page).
    x0, y0, x1, y1 = _one(270)
    assert (x0, x1) == pytest.approx((93 / 1584, 116 / 1584)) and (y0, y1) == pytest.approx(
        (1 - 320 / 1224, 1 - 102 / 1224))
    for none in (None, -1, 0):
        assert _one(none) == pytest.approx([102 / 1224, 93 / 1584, 320 / 1224, 116 / 1584])
    flipped = _one(180)
    assert flipped == pytest.approx([1 - 320 / 1224, 1 - 116 / 1584, 1 - 102 / 1224, 1 - 93 / 1584])


def test_a_label_the_model_does_not_have_fails_the_blocks_only():
    raw = _raw()
    odd = {"block_label": "brand_new", "block_bbox": [0, 0, 5, 5], "block_content": "x"}
    outs, errs = _parse({**raw, "parsing_res_list": [*raw["parsing_res_list"], odd]})
    assert "blocks" in errs and "brand_new" in str(errs["blocks"]) and outs["html"]


def test_html_only_asks_for_no_blocks_and_the_furniture_option_is_sent():
    outs, errs = _parse(_raw(), frozenset({"html"}))
    assert errs == {} and set(outs) == {"html"}
    sent = pp.PpStructureV3(furniture=False).requests(frozenset({"html"}))[0].sent
    assert sent["settings"] == {"furniture": False} and sent["package"].startswith("paddleocr==")


def test_the_adapters_pinned_models_are_the_ones_the_images_pins_file_holds():
    import ast

    src = Path(pp.__file__).parent / "serve" / "pp-structurev3" / "model_pins.py"
    (assign,) = [n for n in ast.parse(src.read_text()).body if isinstance(n, ast.Assign)]
    assert ast.literal_eval(assign.value) == pp.PINNED
    assert all(len(sha) == 40 for sha in pp.PINNED.values())


def test_cpu_server_pins_paddle_322_for_the_one_dnn_pir_regression():
    dockerfile = Path(pp.__file__).parent / "serve" / "pp-structurev3" / "Dockerfile"
    lines = dockerfile.read_text().splitlines()
    assert any("Paddle#77340" in line and "oneDNN+PIR" in line for line in lines)
    assert any(line.startswith("RUN pip install") and "paddlepaddle==3.2.2" in line for line in lines)


def test_adapter_package_declaration_matches_the_cpu_server_paddle_pin():
    dockerfile = Path(pp.__file__).parent / "serve" / "pp-structurev3" / "Dockerfile"
    install = next(line for line in dockerfile.read_text().splitlines() if line.startswith("RUN pip install"))
    docker_version = re.search(r"paddlepaddle==([0-9.]+)", install)
    adapter_version = re.search(r"paddlepaddle ([0-9.]+)", pp.PACKAGE)
    assert docker_version and adapter_version and docker_version.group(1) == adapter_version.group(1)


def test_a_vision_footnote_block_is_a_footnote():
    raw = _raw()
    raw["parsing_res_list"][0]["block_label"] = "vision_footnote"
    outs, errs = _parse(raw)
    assert errs == {} and outs["blocks"][0]["label"] == "footnote"


def test_gpu_server_pins_the_same_paddle_version_from_the_cu126_index():
    serve = Path(pp.__file__).parent / "serve" / "pp-structurev3"
    gpu = (serve / "Dockerfile.gpu").read_text()
    assert "paddlepaddle-gpu==3.2.2" in gpu and "/packages/stable/cu126/" in gpu
    assert "paddlepaddle==3.2.2" in (serve / "Dockerfile").read_text()
    assert '"paddlepaddle", "paddlepaddle-gpu"' in (serve / "server.py").read_text()
