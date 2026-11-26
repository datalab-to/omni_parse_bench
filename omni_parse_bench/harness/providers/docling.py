"""Docling (docling-project/docling), served from providers/serve/docling/ on any host, on its GPU if any.

Licenses, from PyPI and the Hugging Face model cards (read 2026-11-25): the `docling` package is MIT;
the layout model docling-project/docling-layout-heron is apache-2.0; the table model
docling-project/docling-models lists cdla-permissive-2.0 and apache-2.0; RapidOCR (`rapidocr`, whose torch
backend runs here, with the PP-OCRv6 models it downloads from ModelScope when the image is built) is
Apache-2.0 on PyPI (its models' own cards are not checked here).
"""
from __future__ import annotations

import dataclasses
from pathlib import Path
from typing import Any, ClassVar

from omni_bench_core import adapter

from .. import contract, errors, http, layout
from ..adapter import Served

SUPPORTS = frozenset({"html", "blocks"})
# Note: the package names its models, so its version decides them; the server's answer says which it ran.
PACKAGE = "docling==2.153.0 (rapidocr==3.10.0)"
# The Hugging Face models it loads, at the commits its server pins: the layout model's default is `main`,
# which the server replaces with this commit; TableFormer's is the tag v2.3.0 in the package's own code,
# this commit.
LAYOUT_WEIGHTS = "docling-project/docling-layout-heron@8f39ad3c0b4c58e9c2d2c84a38465abf757272d8"
TABLE_WEIGHTS = "docling-project/docling-models@fc0f2d45e2218ea24bce5045f58a389aed16dc23"
# Docling's DocItemLabel (docling_core.types.doc.labels) onto views.LABELS, as the other vendors' types map.
LABELS = {
    "text": "text", "paragraph": "text", "reference": "text", "handwritten_text": "text",
    "document_index": "text",  # a table of contents, as Datalab's TableOfContents is text
    "title": "heading", "section_header": "heading",
    "page_header": "page_furniture", "page_footer": "page_furniture",
    "list_item": "list", "caption": "caption", "footnote": "footnote", "formula": "equation", "code": "code",
    "table": "table",
    "form": "form", "key_value_region": "form",
    # a checkbox is a form field, as LlamaParse's are
    "checkbox_selected": "form", "checkbox_unselected": "form",
    "picture": "figure", "chart": "figure",
}
# Labels Docling can give that no view label is clearly the same kind as: these items are left out of the
# blocks (never guessed), and stay in the html. The field_* labels are the parts of a field_region or a form,
# which has its own block; `marker` is a list's bullet or number, whose item has its own block.
DROPPED = frozenset({"grading_scale", "empty_value", "field_region", "field_heading", "field_item",
                     "field_key", "field_value", "field_hint", "marker", "track"})


@dataclasses.dataclass(frozen=True)
class Docling(Served):
    """Where the Docling server (serve/docling/) answers, and whether the page's headers and footers are kept.

    Run as Docling's own quickstart runs it: `DocumentConverter().convert(file)`, its standard PDF pipeline
    at its default options (docling 2.153.0), so the package's defaults decide everything else (OCR on, with
    the engine `auto` picks, RapidOCR here; table structure on; formula and code enrichment off). Steps 1 to 4
    run on the server
    (serve/docling/server.py); step 5 runs here, with no vendor code.

    How a page is processed:

      1. Input loading        opb sends the page file. A PDF's first page is read by the pipeline's PDF
                              backend (its text layer, OCR for the bitmap areas); an image file is read as
                              it is.
      2. Image preprocessing  the pipeline's: the page rendered for layout analysis, OCR and table
                              structure.
      3. Model inference      the layout model (docling-layout-heron), OCR where the page has no text layer,
                              and the table model (TableFormer), all on Docling's default device (below).
                              The two Hugging Face models are at exact commits (LAYOUT_WEIGHTS,
                              TABLE_WEIGHTS), which /served reports.
      4. Vendor output parsing  the `DoclingDocument`: its items in reading order, each with a label and a
                              box on the page, exported by the document's own `export_to_html`; the page's
                              header and footer items (the furniture layer, which the export leaves out by
                              default) are included.
      5. Mapping to opb outputs  html is that export, as it is; blocks are each item's label (LABELS) and
                              box divided by the page's size. An item whose label is in DROPPED is no block.

    Differences from the vendor:

      - the furniture layer is exported with the body, so page headers and footers are kept, as every other
        adapter keeps them. `included_content_layers` is the export's option for this (docling docs,
        usage/advanced_options.md: "to include them in an export, pass the extra layers explicitly (this
        applies to any `DoclingDocument`)"; the default is the body alone; `furniture` is defined in
        concepts/docling_document.md);
      - the layout model is pinned to a commit: its spec's revision is `main` by default (the `revision` field
        of `PdfPipelineOptions().layout_options.model_spec`, in docling's source; the docs do not mention it).

    Its device is Docling's default, as the vendor's: `AcceleratorOptions().device` is `auto`
    (docling/datamodel/accelerator_options.py, in docling-slim 2.153.0, which `docling` installs), and
    `decide_device` (docling/utils/accelerator_utils.py) resolves `auto` to `cuda:0` when torch has CUDA, else
    `mps`, else `xpu`, else the CPU. The image's torch is a CUDA 12.8 build, so with `--gpus` the models run
    on the GPU and without it on the CPU. OCR is on the same device: `auto` OCR
    (docling/models/stages/ocr/auto_ocr_model.py) takes RapidOCR on onnxruntime only when onnxruntime is
    installed, which `docling` does not install, so here it is RapidOCR's torch backend, which
    rapid_ocr_model.py sets to CUDA whenever the device is CUDA.
    `DOCLING_DEVICE=cpu` (docker run -e) keeps a GPU host on the CPU.

        docker build -t opb-docling omni_parse_bench/harness/providers/serve/docling
        docker run --gpus all -p 8001:8001 opb-docling     # without --gpus it runs on the CPU
        opb init docling > config.yaml
        opb run --config config.yaml --set system.docling.base_url=http://localhost:8001 \\
            --set rows.sample=20
    """

    base_url: str = "http://127.0.0.1:8001"
    served: dict[str, Any] = dataclasses.field(
        default_factory=lambda: {"weights": f"{LAYOUT_WEIGHTS}, {TABLE_WEIGHTS}",
                                 "revision": "docling==2.153.0"},
        metadata={"help": "what its server serves: its models at their commits, and the package"})
    furniture: bool = dataclasses.field(default=True, metadata={
        "help": "keep page headers and footers (its furniture layer, left out of the export by default)"})

    name: ClassVar[str] = "docling"
    SUPPORTS: ClassVar[frozenset[str]] = SUPPORTS
    ENV: ClassVar[str] = http.ENDPOINT_KEY
    SERVE: ClassVar[str | None] = "docling"

    def requests(self, wants: frozenset[str]) -> list[contract.Request]:
        return requests(wants, self)

    def send(self, page: Path, request: contract.Request, *, timeout: float) -> contract.Call:
        return call(page, request, timeout=timeout, config=self)

    def parse(self, raw: Any, request: contract.Request) -> tuple[dict, dict]:
        return parse(raw, request, self)


def requests(wants: frozenset[str], config: Docling) -> list[contract.Request]:
    """One call answers both outputs."""
    if not wants: return []
    sent = {"package": PACKAGE, "pipeline": "DocumentConverter() (standard PDF pipeline, defaults)",
            "settings": http.settings(config), "page": "the file, read by its converter"}
    return [contract.Request(frozenset(wants) & SUPPORTS, sent)]


def call(page: Path, request: contract.Request, *, timeout: float = 900.0, config: Docling) -> contract.Call:
    return contract.Call(http.parse(config, page, timeout))


def blocks(raw: dict) -> list[dict]:
    """The document's items as blocks, in the page's frame, the labels in DROPPED left out."""
    frame = (raw["page"]["width"], raw["page"]["height"])
    return [layout.block(layout.label(LABELS, b["label"]), b["bbox"], frame, " ".join(b["text"].split()))
            for b in raw["items"] if b["label"] not in DROPPED]


def parse(raw: dict, request: contract.Request, config: Docling | None = None) -> tuple[dict, dict]:
    status = raw.get("status")
    if (status is not None and str(status).lower().rsplit(".", 1)[-1] != "success") or raw.get("errors"):
        message = f"Docling conversion failed: status={status!r}, errors={raw.get('errors')!r}"
        raise errors.SystemFailed(message, status=200, body=raw)
    if "html" not in raw:
        raise errors.SystemFailed(f"no html in the answer: {str(raw)[:300]}", status=200)
    outputs, errs = {}, {}
    if "html" in request.outputs:
        outputs["html"] = raw["html"]
    if "blocks" in request.outputs:
        try:
            with adapter.reading("the document's items"):
                outputs["blocks"] = blocks(raw)
        except errors.SystemFailed as exc:
            errs["blocks"] = errors.unread(exc)
    return outputs, errs
