"""Docling's adapter: its label table covers every label the package can give, and a block it cannot place
is left out or fails the page, never guessed. The server's reading of a document is checked where docling is
installed (it is not an opb dependency)."""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path

import pytest

from omni_parse_bench import views
from omni_parse_bench.harness import contract
from omni_parse_bench.harness.providers import docling

FIXTURE = Path(__file__).parent / "fixtures" / "open_weights" / "docling.json"
SERVER = Path(docling.__file__).parent / "serve" / "docling" / "server.py"


def _raw() -> dict:
    return json.loads(FIXTURE.read_text())["raw"]


def _parse(raw: dict, outputs=frozenset({"html", "blocks"}), **options):
    config = docling.Docling(**options)
    (asked,) = config.requests(outputs)
    return config.parse(raw, contract.Request(asked.outputs, asked.sent))


def test_every_label_maps_to_a_view_label_and_none_is_both_mapped_and_dropped():
    assert set(docling.LABELS.values()) <= set(views.LABELS)
    assert not set(docling.LABELS) & docling.DROPPED


def test_every_label_the_package_can_give_is_mapped_or_dropped_on_purpose():
    labels = pytest.importorskip("docling_core.types.doc.labels")
    unknown = {label.value for label in labels.DocItemLabel} - set(docling.LABELS) - docling.DROPPED
    assert not unknown, f"decide the label of {sorted(unknown)} (docs/providers.md): LABELS or DROPPED"


def test_html_is_doclings_export_as_it_is_and_blocks_are_its_items_on_the_page():
    raw = _raw()
    outs, errs = _parse(raw)
    assert errs == {} and outs["html"] == raw["html"]
    assert "Example 4.28" in views.text(outs["html"])
    kept = [b for b in raw["items"] if b["label"] not in docling.DROPPED]
    assert [b["label"] for b in outs["blocks"]] == [docling.LABELS[b["label"]] for b in kept]
    assert all(0 <= x <= 1 for b in outs["blocks"] for x in b["bbox"])
    head = outs["blocks"][0]
    assert head["label"] == "page_furniture" and head["bbox"][1] < 0.2


def test_an_item_with_a_dropped_label_is_not_a_block_and_an_unknown_one_fails_the_blocks_only():
    raw = _raw()
    item = {"label": "field_key", "text": "Name", "bbox": [0, 0, 10, 10], "page_no": 1, "layer": "body"}
    outs, errs = _parse({**raw, "items": [*raw["items"], item]})
    assert errs == {} and len(outs["blocks"]) == len(_parse(raw)[0]["blocks"])
    outs, errs = _parse({**raw, "items": [*raw["items"], {**item, "label": "brand_new"}]})
    assert "blocks" in errs and "brand_new" in str(errs["blocks"]) and outs["html"] == raw["html"]


def test_html_only_asks_for_no_blocks():
    outs, errs = _parse(_raw(), frozenset({"html"}))
    assert errs == {} and set(outs) == {"html"}


def test_partial_success_with_errors_fails_the_page_and_keeps_the_raw_reply():
    raw = {**_raw(), "status": "PARTIAL_SUCCESS",
           "errors": [{"component_type": "ocr", "error_message": "stage failed"}]}
    with pytest.raises(docling.errors.SystemFailed) as exc:
        _parse(raw)
    assert exc.value.body == raw
    assert "stage failed" in str(exc.value)


def test_the_furniture_option_is_sent_to_the_server():
    sent = docling.Docling(furniture=False).requests(frozenset({"html"}))[0].sent
    assert sent["settings"] == {"furniture": False} and sent["package"].startswith("docling==")


@pytest.mark.skipif(not all(importlib.util.find_spec(m) for m in ("docling_core", "fastapi")),
                    reason="docling and fastapi are the server's, not opb's")
def test_the_server_reads_a_documents_boxes_from_the_top_left_and_its_tables_cells(monkeypatch):
    from docling_core.types.doc import (BoundingBox, CoordOrigin, ContentLayer, DocItemLabel, DoclingDocument,
                                        ProvenanceItem, Size, TableCell, TableData)

    monkeypatch.setattr("importlib.metadata.version", lambda package: f"{package}==test")
    spec = importlib.util.spec_from_file_location("docling_server", SERVER)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    doc = DoclingDocument(name="d")
    doc.add_page(page_no=1, size=Size(width=100, height=200))
    box = BoundingBox(l=10, b=150, r=60, t=190, coord_origin=CoordOrigin.BOTTOMLEFT)
    doc.add_text(label=DocItemLabel.TEXT, text="hello",
                 prov=ProvenanceItem(page_no=1, bbox=box, charspan=(0, 5)))
    doc.add_text(label=DocItemLabel.PAGE_FOOTER, text="foot", content_layer=ContentLayer.FURNITURE,
                 prov=ProvenanceItem(page_no=1, bbox=box, charspan=(0, 4)))
    cells = [TableCell(text=t, start_row_offset_idx=0, end_row_offset_idx=1, start_col_offset_idx=i,
                       end_col_offset_idx=i + 1) for i, t in enumerate("ab")]
    doc.add_table(data=TableData(table_cells=cells, num_rows=1, num_cols=2),
                  prov=ProvenanceItem(page_no=1, bbox=box, charspan=(0, 0)))
    body = server.items(doc, {ContentLayer.BODY})
    assert [i["label"] for i in body] == ["text", "table"]
    assert body[0]["bbox"] == [10, 10, 60, 50] and body[1]["text"] == "a b"
    assert [i["label"] for i in server.items(doc, {ContentLayer.BODY, ContentLayer.FURNITURE})] == [
        "text", "page_footer", "table"]
    import json
    from types import SimpleNamespace

    result = SimpleNamespace(document=doc, status=SimpleNamespace(value="success"), errors=[])
    raw = server.result_payload(result, {ContentLayer.BODY, ContentLayer.FURNITURE})
    reread = DoclingDocument.model_validate(json.loads(json.dumps(raw["docling_document"])))
    labels = [item.label.value for item, _ in reread.iterate_items(
        included_content_layers={ContentLayer.BODY, ContentLayer.FURNITURE})]
    assert labels == ["text", "page_footer", "table"]


@pytest.mark.skipif(not all(importlib.util.find_spec(m) for m in ("docling_core", "fastapi")),
                    reason="docling and fastapi are the server's, not opb's")
@pytest.mark.parametrize(("status", "errors", "pages", "raise_export"), [
    ("partial_success", [{"stage": "ocr", "error": "failed"}], {}, False),
    ("success", [], {1: object()}, True),
])
def test_parse_route_returns_failure_status_and_errors_before_document_export(
        monkeypatch, status, errors, pages, raise_export):
    from fastapi.testclient import TestClient
    import sys
    from types import SimpleNamespace

    monkeypatch.setattr("importlib.metadata.version", lambda package: f"{package}==test")
    spec = importlib.util.spec_from_file_location("docling_server", SERVER)
    server = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, server)
    spec.loader.exec_module(server)

    class FakeDocument:
        def __init__(self):
            self.pages = pages

        def export_to_html(self, **kwargs):
            if raise_export: raise RuntimeError("HTML export exploded")

        def export_to_markdown(self, **kwargs):
            return ""

        def export_to_dict(self):
            return {}

    result = SimpleNamespace(document=FakeDocument(), status=SimpleNamespace(value=status), errors=errors)

    class FakeConverter:
        def convert(self, *args, **kwargs):
            return result

    monkeypatch.setattr(server, "_converter", FakeConverter())
    response = TestClient(server.app).post("/parse", json={"page": "eA==", "suffix": ".pdf",
                                                           "settings": {"furniture": True}})
    assert response.status_code == 200
    raw = response.json()
    assert raw["status"] == status
    if errors:
        assert raw["errors"] == errors
    else:
        assert raw["errors"] == [{"stage": "server_export", "error": "HTML export exploded"}]
    with pytest.raises(docling.errors.SystemFailed):
        _parse(raw)


def _start(tmp_path: Path, monkeypatch, *, cuda: bool, **env) -> list[str]:
    """start.sh's uvicorn arguments, with a `python` that says whether torch finds CUDA and a `uvicorn` that
    prints its arguments (no torch, docling or GPU needed)."""
    import subprocess

    for name, body in (("python", f"exit {0 if cuda else 1}"), ("uvicorn", 'echo "$@"')):
        stub = tmp_path / name
        stub.write_text(f"#!/bin/sh\n{body}\n")
        stub.chmod(0o755)
    monkeypatch.delenv("WORKERS", raising=False)
    monkeypatch.delenv("DOCLING_DEVICE", raising=False)
    environ = {**os.environ, "PATH": f"{tmp_path}{os.pathsep}{os.environ['PATH']}", **env}
    out = subprocess.run(["bash", str(SERVER.parent / "start.sh")], env=environ, capture_output=True,
                         text=True, check=True).stdout
    return out.split()


def test_the_image_leaves_the_device_to_docling_and_its_torch_has_cuda():
    dockerfile = (SERVER.parent / "Dockerfile").read_text()
    env = [line for line in dockerfile.splitlines() if line.startswith("ENV")]
    assert env and not [line for line in env if "DOCLING_DEVICE" in line]
    assert "whl/cu128" in dockerfile and "torch==2.11.0+cu128" in dockerfile


@pytest.mark.parametrize(("cuda", "env", "workers"), [
    (True, {}, "4"), (False, {}, "2"), (True, {"DOCLING_DEVICE": "cpu"}, "2"), (True, {"WORKERS": "3"}, "3"),
    (False, {"WORKERS": "1"}, "1")])
def test_the_server_starts_4_workers_on_a_gpu_2_on_the_cpu_or_the_workers_asked(tmp_path, monkeypatch, cuda,
                                                                                   env, workers):
    args = _start(tmp_path, monkeypatch, cuda=cuda, **env)
    assert args[args.index("--workers") + 1] == workers


def test_the_servers_converter_is_on_doclings_default_device_auto(monkeypatch):
    pytest.importorskip("docling")
    from docling.datamodel.accelerator_options import AcceleratorOptions
    from docling.datamodel.base_models import InputFormat

    monkeypatch.delenv("DOCLING_DEVICE", raising=False)
    spec = importlib.util.spec_from_file_location("docling_server", SERVER)
    server = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(server)
    assert AcceleratorOptions().device == "auto"
    options = server.make_converter().format_to_options[InputFormat.PDF].pipeline_options
    assert options.accelerator_options.device == "auto"
