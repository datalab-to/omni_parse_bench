"""Docling's adapter: its label table covers every label the package can give, and a block it cannot place
is left out or fails the page, never guessed. The server's reading of a document is checked where docling is
installed (it is not an opb dependency)."""
from __future__ import annotations

import importlib.util
import json
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


def test_the_furniture_option_is_sent_to_the_server():
    sent = docling.Docling(furniture=False).requests(frozenset({"html"}))[0].sent
    assert sent["settings"] == {"furniture": False} and sent["package"].startswith("docling==")


@pytest.mark.skipif(not all(importlib.util.find_spec(m) for m in ("docling_core", "fastapi")),
                    reason="docling and fastapi are the server's, not opb's")
def test_the_server_reads_a_documents_boxes_from_the_top_left_and_its_tables_cells():
    from docling_core.types.doc import (BoundingBox, CoordOrigin, ContentLayer, DocItemLabel, DoclingDocument,
                                        ProvenanceItem, Size, TableCell, TableData)

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
