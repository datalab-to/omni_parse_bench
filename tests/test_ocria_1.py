"""OCRia-1: the request vLLM is sent and a reply read, without model weights.

The replies here are synthetic: written to follow the output format its model card documents (Markdown in a
```markdown fence, tables as HTML, `<page_header>`, `<page_footer>`, `<page_number>` and `<watermark>` tags,
images as `![label: description]`, diagrams as a ```mermaid block). They are not the model's own answers.
"""
from __future__ import annotations

import hashlib
import io

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


def test_it_has_html_only_and_is_never_asked_for_blocks():
    api = harness.system("ocria-1")
    assert api.SUPPORTS == frozenset({"html"}) and api.SERVE == "ocria-1"
    assert api.requests(frozenset({"blocks"})) == []
    (request,) = api.requests(frozenset({"html", "blocks"}))
    assert request.outputs == frozenset({"html"})
    assert request.sent["weights"] == "llamaindex/OCRia-1"
    assert request.sent["prompt_sha256"] == ocria_1.PROMPT_SHA256
    assert request.sent["settings"] == {"temperature": 0.0, "max_tokens": 24576, "dpi": 300,
                                        "pixels": 4_100_000}


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


def test_a_page_that_wants_blocks_is_asked_for_html_alone(downloaded, tmp_path, monkeypatch):
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
