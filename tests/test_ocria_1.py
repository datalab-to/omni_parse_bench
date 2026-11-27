"""OCRia-1: the request vLLM is sent and a reply read, without model weights.

The replies here are synthetic: written to follow the output format its model card documents (Markdown in a
```markdown fence, tables as HTML, `<page_header>`, `<page_footer>`, `<page_number>` and `<watermark>` tags,
images as `![label: description]`, diagrams as a ```mermaid block). They are not the model's own answers.
"""
from __future__ import annotations

import base64
import hashlib
import io
from pathlib import Path

import pytest
from omni_bench_core import adapter as core

from omni_parse_bench import harness, views
from omni_parse_bench.harness import errors, http
from omni_parse_bench.harness.providers import llm, ocria_1

SERVED = {"weights": "llamaindex/OCRia-1", "revision": ocria_1.REVISION}
ANSWER = """```markdown
<watermark>DRAFT</watermark>
<page_header>Annual Report 2025</page_header>

# Results

Revenue grew by **12%** in H<sub>2</sub>.

![logo: Acme Corp]

<table><tr><th colspan="2">Sales</th></tr><tr><td>2024</td><td>12</td></tr></table>

```mermaid
graph TD
  A["![x]"] --> B
```

![chart: sales by year]
<page_footer>Confidential <page_number>7</page_number></page_footer>
```"""


def reply(text, finish="stop"):
    return {"choices": [{"message": {"content": text}, "finish_reason": finish}],
            "usage": {"prompt_tokens": 1500, "completion_tokens": 300}}


PROMPT = "Transcribe this Page in markdown (a stand-in: the real text is fetched, only its hash is kept)\n"


@pytest.fixture
def downloaded(tmp_path, monkeypatch):
    """`hf_hub_download` answering with a file of the given text, recording what it was asked for."""
    import huggingface_hub

    asked = []

    def fake(repo, name, revision=None, **kw):
        asked.append((repo, name, revision))
        (path := tmp_path / "prompt.txt").write_text(PROMPT)
        return str(path)

    monkeypatch.setattr(huggingface_hub, "hf_hub_download", fake)
    monkeypatch.setattr(ocria_1, "PROMPT_SHA256", hashlib.sha256(PROMPT.encode()).hexdigest())
    return asked


def test_the_prompt_is_fetched_at_the_pinned_revision_and_its_hash_checked(downloaded, monkeypatch):
    assert ocria_1.prompt() == PROMPT
    assert downloaded == [("llamaindex/OCRia-1", "prompt.txt", ocria_1.REVISION)]
    monkeypatch.setattr(ocria_1, "PROMPT_SHA256", "0" * 64)
    with pytest.raises(ValueError, match="sha256"):
        ocria_1.prompt()


def test_the_expected_prompt_hash_is_the_cards_at_the_pinned_revision():
    assert ocria_1.PROMPT_SHA256 == "907944f61490bf666cc93129d93d1537d9d6f872cc285c371c7889700b6f3e38"
    assert len(ocria_1.PROMPT_SHA256) == 64


def test_it_has_blocks_only_with_layout_on():
    api = harness.system("ocria-1")
    assert api.SUPPORTS == frozenset({"html", "blocks"}) and api.SERVE == "ocria-1"
    assert api.requests(frozenset({"blocks"})) == []
    (request,) = api.requests(frozenset({"html", "blocks"}))
    assert request.outputs == frozenset({"html"}) and "layout" not in request.sent
    assert request.sent["weights"] == "llamaindex/OCRia-1"
    assert request.sent["prompt_sha256"] == ocria_1.PROMPT_SHA256
    # the box server's options are the adapter's own, not the model's: the html call is sent as before
    assert request.sent["settings"] == {"temperature": 0.0, "max_tokens": 24576, "dpi": 300,
                                        "pixels": 4_100_000}
    boxed = harness.system("ocria-1", {"layout": True})
    (request,) = boxed.requests(frozenset({"html", "blocks"}))
    assert request.outputs == frozenset({"html", "blocks"})
    assert request.sent["settings"] == {"temperature": 0.0, "max_tokens": 24576, "dpi": 300,
                                        "pixels": 4_100_000}
    assert request.sent["layout"]["grounding"] == f"llamaindex/OCRia-1@{ocria_1.REVISION}"
    assert request.sent["layout"]["detector"] == f"{ocria_1.DETECTOR}@{ocria_1.DETECTOR_REVISION}"
    # a page that wants blocks alone still gets its one chat call: the boxes place its answer
    (request,) = boxed.requests(frozenset({"blocks"}))
    assert request.outputs == frozenset({"blocks"})
    assert boxed.requests(frozenset({"markdown"})) == []


def test_the_request_is_the_model_cards(downloaded, tmp_path, monkeypatch):
    from PIL import Image

    got = {}
    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@" + ocria_1.REVISION, SERVED))
    monkeypatch.setattr(llm, "chat", lambda url, body, *a, **k: got.update(body, url=url) or reply("# T"))
    Image.new("RGB", (200, 300), "white").save(page := tmp_path / "p.png")
    config = harness.system("ocria-1", {"base_url": "http://gpu:9000"})
    call = ocria_1.call(page, config.requests(frozenset({"html"}))[0], config=config)
    assert got["url"] == "http://gpu:9000/v1"
    assert got["model"] == "llamaindex/OCRia-1@" + ocria_1.REVISION and call.raw["served"] == SERVED
    system, user = got["messages"]
    assert system == {"role": "system", "content": PROMPT}
    # one page image, no user text
    assert user["role"] == "user" and [p["type"] for p in user["content"]] == ["image_url"]
    assert user["content"][0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert got["temperature"] == 0.0 and got["max_tokens"] == 24576
    assert got["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
    assert call.raw["prompt_sha256"] == ocria_1.PROMPT_SHA256
    assert (call.cost.tokens_in, call.cost.tokens_out) == (1500, 300)


def test_a_page_over_the_pixel_budget_is_scaled_down_and_a_smaller_one_is_not(tmp_path):
    from PIL import Image

    config = harness.system("ocria-1")
    Image.new("RGB", (3000, 2000), "white").save(big := tmp_path / "big.png")   # 6 MP
    Image.new("RGB", (1000, 1400), "white").save(small := tmp_path / "small.png")
    scaled = Image.open(io.BytesIO(ocria_1.image(big, config)))
    assert scaled.width * scaled.height <= 4_100_000 * 1.001
    assert scaled.width / scaled.height == pytest.approx(1.5, abs=0.01)
    assert abs(scaled.width * scaled.height - 4_100_000) < 20_000
    assert Image.open(io.BytesIO(ocria_1.image(small, config))).size == (1000, 1400)


def test_a_pdf_is_rendered_at_300_dpi(tmp_path):
    import pypdfium2 as pdfium
    from PIL import Image

    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(pdf := tmp_path / "p.pdf")
    doc.close()
    # 612 x 792 pt at 300 DPI is 2550 x 3300 px (8.4 MP): kept at a 10 MP budget, scaled at the 4.1 MP one
    full = Image.open(io.BytesIO(ocria_1.image(pdf, harness.system("ocria-1", {"pixels": 10_000_000}))))
    assert abs(full.width - 2550) <= 1 and abs(full.height - 3300) <= 1  # pdfium rounds up
    capped = Image.open(io.BytesIO(ocria_1.image(pdf, harness.system("ocria-1"))))
    # the card's rounding of each side may pass the budget by a few hundred pixels
    assert capped.width * capped.height <= 4_100_000 * 1.001 and capped.height > capped.width


def test_the_documented_answer_is_read_as_html():
    (request,) = harness.system("ocria-1").requests(frozenset({"html"}))
    outs, errs = ocria_1.parse(reply(ANSWER), request)
    html = outs["html"]
    assert errs == {} and "<h1>Results</h1>" in html and "<strong>12%</strong>" in html
    assert "H<sub>2</sub>" in html
    # the page's furniture stays in the page, as text, with no tag of the model's own
    text = views.text(html, alt=False)
    for kept in ("DRAFT", "Annual Report 2025", "Confidential", "7"):
        assert kept in text
    for tag in ("page_header", "page_footer", "page_number", "watermark"):
        assert tag not in html
    assert "<p>Annual Report 2025</p>" in html
    # a table stays a table, with its spans
    assert '<th colspan="2">Sales</th>' in html and "<td>12</td>" in html
    # an image is alt text, not page text
    assert '<img alt="logo: Acme Corp">' in html and '<img alt="chart: sales by year">' in html
    assert "Acme Corp" not in views.text(html, alt=False)
    # a listing inside the page is kept whole, its own text untouched
    assert "graph TD" in html and '![x]' in html and "```" not in html


def test_a_reply_cut_at_the_token_limit_is_read_as_it_is_and_another_stop_fails():
    (request,) = harness.system("ocria-1").requests(frozenset({"html"}))
    cut = reply("```markdown\n# Title\n\nbody", finish="length")
    assert "Title" in views.text(ocria_1.parse(cut, request)[0]["html"])
    with pytest.raises(errors.SystemFailed):
        ocria_1.parse(reply("text", finish="abort"), request)
    with pytest.raises(errors.SystemFailed, match="empty"):
        ocria_1.parse(reply("  "), request)


def test_a_page_that_wants_blocks_is_asked_for_html_alone_without_layout(downloaded, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    record = core.predict(harness.system("ocria-1"), harness.Input(page, frozenset({"html", "blocks"})))
    [out] = record["output"]["pages"]
    assert list(out) == ["html"] and "Results" in views.text(out["html"])


def test_the_options_that_shape_the_image_name_the_run():
    from omni_bench_core import run as runs

    def folder(**options):
        return runs.identity(harness.system("ocria-1", options), {"dataset": "d", "task": "parse"})

    assert folder() != folder(dpi=200) and folder() != folder(pixels=2_000_000)
    assert folder() != folder(layout=True)
    # where the box server is, like where vLLM is, is not part of the question
    assert folder(layout=True) == folder(layout=True, grounding_url="http://gpu:9100")


def test_the_box_venv_keeps_the_image_torch_and_torchvision():
    build = Path(ocria_1.__file__).parent / "serve" / "ocria-1"
    dockerfile = (build / "Dockerfile").read_text()
    override = (build / "no-torch.txt").read_text()
    assert "COPY no-torch.txt /srv/no-torch.txt" in dockerfile
    assert "uv pip install --python /opt/boxes/bin/python --override /srv/no-torch.txt" in dockerfile
    assert 'torch; python_version < "0"' in override
    assert 'torchvision; python_version < "0"' in override


# --- layout boxes: a stand-in box server, answering as the card's serve_boxes.py does (items in pixels of the
# image it was sent), plus what serve/ocria-1/boxes.py adds (`served`)

BOX_SERVED = {"weights": "llamaindex/OCRia-1", "revision": ocria_1.REVISION, "detector": ocria_1.DETECTOR,
              "detector_revision": ocria_1.DETECTOR_REVISION, "transformers": "5.22.2"}


def items(width, height):
    return [
        {"type": "Page-header", "label": "header", "md": "Annual Report 2025", "box": [10, 5, 190, 20],
         "start": 0},
        {"type": "Section-header", "label": "paragraph_title", "md": "# Results", "box": [10, 30, 100, 45],
         "start": 30},
        {"type": "Text", "label": "text", "md": "Revenue grew by **12%** in H<sub>2</sub>.",
         "box": [10, 50, width, 70], "start": 40},
        {"type": "Table", "label": "table", "md": "<table><tr><td>2024</td><td>12</td></tr></table>",
         "box": [10, 80, 190, 150], "start": 90},
        {"type": "Picture", "label": "image", "md": "![chart: sales by year]", "box": [10, 160, 100, 250],
         "start": 120},
        {"type": "Key-Value Region", "label": "text", "md": "Total: $5", "box": [110, 160, 190, 170],
         "start": 150},
        {"type": "Page-footer", "label": "footer", "md": "Confidential 7", "box": [10, 280, 190, 290],
         "start": 160},
        {"type": "Text", "label": "text", "md": "no area", "box": [50, 50, 50, 60], "start": 170},
    ]


@pytest.fixture
def box_server():
    """A box server on a free port: records each request, answers with `items` (or `said` overrides)."""
    import json
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    from PIL import Image

    state = {"asked": [], "served": dict(BOX_SERVED), "status": 200}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            req = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["asked"].append((self.path, req))
            w, h = Image.open(io.BytesIO(base64.b64decode(req["image_png_b64"]))).size
            # the prompt the server loaded is the one the adapter checks (a test's stand-in, when patched)
            served = {"prompt_sha256": ocria_1.PROMPT_SHA256, **state["served"]}
            body = json.dumps({"width": w, "height": h, "items": items(w, h), "served": served}
                              if state["status"] == 200 else {"error": "RuntimeError('boom')"}).encode()
            self.send_response(state["status"])
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    state["url"] = f"http://127.0.0.1:{srv.server_address[1]}"
    yield state
    srv.shutdown()


def boxed(box_server, **options):
    return harness.system("ocria-1", {"layout": True, "grounding_url": box_server["url"], **options})


def test_the_box_server_is_sent_the_image_the_answer_came_from_the_raw_answer_and_the_pdf(
        downloaded, box_server, tmp_path, monkeypatch):
    import pypdfium2 as pdfium
    from PIL import Image

    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(pdf := tmp_path / "p.pdf")
    doc.close()
    sent = {}
    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@" + ocria_1.REVISION, SERVED))
    monkeypatch.setattr(llm, "chat", lambda url, body, *a, **k: sent.update(body) or reply(ANSWER))
    config = boxed(box_server)
    call = ocria_1.call(pdf, config.requests(frozenset({"html", "blocks"}))[0], config=config)
    [(path, req)] = box_server["asked"]
    assert path == "/ground"
    # the exact PNG vLLM was sent, the raw answer (fence and tags as the model wrote them), the page itself
    url = sent["messages"][1]["content"][0]["image_url"]["url"]
    assert url == "data:image/png;base64," + req["image_png_b64"]
    assert req["answer"] == ANSWER
    assert base64.b64decode(req["pdf_b64"]) == pdf.read_bytes()
    # its words are read at 300 DPI, in the frame of the render before the 4.1 MP scale-down
    assert req["dpi"] == 300
    assert abs(req["render_size"][0] - 2550) <= 1 and abs(req["render_size"][1] - 3300) <= 1
    w, h = Image.open(io.BytesIO(base64.b64decode(req["image_png_b64"]))).size
    assert w * h <= 4_100_000 * 1.001
    assert call.raw["layout"]["width"] == w and call.raw["layout"]["served"]["detector"] == ocria_1.DETECTOR
    # an image has no text layer: its words come from attention
    Image.new("RGB", (200, 300), "white").save(png := tmp_path / "p.png")
    ocria_1.call(png, config.requests(frozenset({"blocks"}))[0], config=config)
    req = box_server["asked"][-1][1]
    assert req["pdf_b64"] is None and req["render_size"] is None


def test_the_items_are_read_as_blocks(downloaded, box_server, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    Image.new("RGB", (200, 300), "white").save(page := tmp_path / "p.png")
    record = core.predict(boxed(box_server), harness.Input(page, frozenset({"html", "blocks"})))
    [out] = record["output"]["pages"]
    assert record["error"] is None and set(out) == {"html", "blocks"}
    assert "Results" in views.text(out["html"])
    got = out["blocks"]
    assert [b["label"] for b in got] == ["page_furniture", "heading", "text", "table", "figure", "form",
                                         "page_furniture"]   # the item with no area is left out
    assert got[0]["bbox"] == [10 / 200, 5 / 300, 190 / 200, 20 / 300]
    assert got[2]["bbox"][2] == 1.0
    # each block's text is what a reader sees of its markdown
    assert got[1]["text"] == "Results" and got[2]["text"] == "Revenue grew by 12% in H2."
    assert got[3]["text"] == "2024 12"
    assert views.blocks(got)   # well formed for the scorer


def test_an_item_type_not_in_labels_fails_the_blocks_alone():
    raw = {**reply(ANSWER), "layout": {"width": 100, "height": 100, "served": BOX_SERVED,
                                         "items": [{"type": "Chart", "md": "x", "box": [0, 0, 10, 10]}]}}
    (request,) = harness.system("ocria-1", {"layout": True}).requests(frozenset({"html", "blocks"}))
    outs, errs = ocria_1.parse(raw, request)
    assert "Results" in views.text(outs["html"]) and "blocks" not in outs
    assert "Chart" in errs["blocks"]
    for heron in ("Text", "Document Index", "Title", "Section-header", "Page-header", "Page-footer",
                  "List-item", "Caption", "Footnote", "Formula", "Code", "Table", "Form",
                  "Key-Value Region", "Picture"):
        assert ocria_1.LABELS[heron] in views.LABELS


def test_a_box_server_with_other_weights_stops_the_run_and_a_failing_one_fails_the_blocks(
        downloaded, box_server, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    config = boxed(box_server)
    (request,) = config.requests(frozenset({"blocks"}))
    box_server["served"] = {**BOX_SERVED, "detector_revision": "main"}
    with pytest.raises(ValueError, match="box server"):
        ocria_1.call(page, request, config=config)
    box_server["served"] = {**BOX_SERVED, "prompt_sha256": "0" * 64}
    with pytest.raises(ValueError, match="box server"):
        ocria_1.call(page, request, config=config)
    box_server["served"] = BOX_SERVED
    # a box server that fails fails the blocks alone: the html of the paid answer stands
    box_server["status"] = 500
    call = ocria_1.call(page, request, config=config)
    assert "HTTP 500" in call.raw["layout"]["error"] and call.raw["layout"]["attempts"] == 2
    (both,) = config.requests(frozenset({"html", "blocks"}))
    outs, errs = ocria_1.parse(call.raw, both)
    assert "Results" in views.text(outs["html"]) and "blocks" not in outs and "HTTP 500" in errs["blocks"]


def test_several_box_servers_take_pages_in_turn():
    config = harness.system("ocria-1", {"layout": True, "grounding_url": "http://a:1, http://b:2/"})
    got = {ocria_1.server(config) for _ in range(4)}
    assert got == {"http://a:1", "http://b:2"}


def test_no_box_server_stops_the_run_and_says_how_to_start_it(downloaded, tmp_path, monkeypatch):
    import socket

    from PIL import Image

    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    api = harness.system("ocria-1", {"layout": True, "grounding_url": f"http://127.0.0.1:{port}"})
    with pytest.raises(Exception) as e:
        core.predict(api, harness.Input(page, frozenset({"html", "blocks"})))
    note = "\n".join(getattr(e.value, "__notes__", []))
    assert f"no box server at http://127.0.0.1:{port}" in note and "boxes.sh" in note, note


def test_the_box_server_scales_text_layer_words_to_the_image_it_was_sent(tmp_path, monkeypatch):
    """boxes.py reads the words with the card's `page_words` at `dpi`, in the frame of a render at `dpi`, and
    scales them to the image the answer came from; the card's own code is stood in for here."""
    import importlib.util
    import sys
    import types

    import pypdfium2 as pdfium

    asked = []

    def page_words(page, dpi):
        asked.append(dpi)
        return [{"text": "Total", "box": [100.0, 200.0, 300.0, 250.0]}]

    pdf_mod = types.ModuleType("ocria_grounding.pdf")
    pdf_mod.page_words = page_words
    monkeypatch.setitem(sys.modules, "ocria_grounding", types.ModuleType("ocria_grounding"))
    monkeypatch.setitem(sys.modules, "ocria_grounding.pdf", pdf_mod)
    path = Path(ocria_1.__file__).parent / "serve" / "ocria-1" / "boxes.py"
    spec = importlib.util.spec_from_file_location("ocria_boxes", path)
    boxes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(boxes)
    doc = pdfium.PdfDocument.new()
    doc.new_page(612, 792)
    doc.save(pdf := tmp_path / "p.pdf")
    doc.close()
    req = {"pdf_b64": base64.b64encode(pdf.read_bytes()).decode(), "dpi": 300, "render_size": [2550, 3300]}
    (w,) = boxes.words(req, (1275, 1650))
    assert asked == [300] and w["text"] == "Total" and w["box"] == [50.0, 100.0, 150.0, 125.0]
    # an image has no text layer: the card's words as sent, or none
    assert boxes.words({"pdf_b64": None}, (10, 10)) is None


def test_a_box_server_that_hangs_fails_the_blocks_within_the_pages_budget(downloaded, tmp_path, monkeypatch):
    import socket
    import time

    from PIL import Image

    hold = socket.socket()
    hold.bind(("127.0.0.1", 0))
    hold.listen(8)   # accepts, never answers
    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    monkeypatch.setattr(ocria_1, "BOX_MARGIN_S", 0.5)
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    api = harness.system("ocria-1", {"layout": True, "grounding_url": f"http://127.0.0.1:{hold.getsockname()[1]}"})
    t0 = time.time()
    record = core.predict(api, harness.Input(page, frozenset({"html", "blocks"})), timeout=3.0)
    hold.close()
    assert time.time() - t0 < 3.0 and record["error"] is None
    [out] = record["output"]["pages"]
    assert "Results" in views.text(out["html"]) and out["blocks"] is None


def test_an_address_that_is_no_box_server_stops_the_run(downloaded, box_server, tmp_path, monkeypatch):
    from PIL import Image

    monkeypatch.setattr(http, "served", lambda *a: ("llamaindex/OCRia-1@x", SERVED))
    monkeypatch.setattr(llm, "chat", lambda *a, **k: reply(ANSWER))
    Image.new("RGB", (64, 64), "white").save(page := tmp_path / "p.png")
    box_server["status"] = 404
    config = boxed(box_server)
    with pytest.raises(ValueError, match="is it a box server"):
        ocria_1.call(page, config.requests(frozenset({"blocks"}))[0], config=config)
