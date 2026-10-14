# Providers

How each vendor becomes an adapter in `omni_parse_bench/harness/providers/`: one module per vendor,
with five names (`contract.Adapter`):

- `Config`: its options;
- `SUPPORTS`: the output types it can produce;
- `requests(wants, config)`: the calls a page needs;
- `call(page, request, *, timeout, config)`: make one call and return the vendor's answer as
  received, with its cost; and
- `parse(raw, request, config)`: read the outputs from an answer.

`registry.ADAPTERS` lists the vendors and the open-weight models with adapters of their own; any
model id goes to `llm.py`.

1. [The two outputs, and how an adapter produces them](#the-two-outputs-and-how-an-adapter-produces-them): html and blocks, and the format changes an adapter may make;
2. [Block labels](#block-labels): each vendor's block types, mapped onto the labels;
3. [The vendors](#the-vendors): each adapter's API, outputs, headers and keys;
4. [Serving an open model](#serving-an-open-model): each open model's folder (image, start script, server) and how opb reaches it;
5. [Open-weight models](#open-weight-models): the open OCR models, their providers and their labels;
6. [What differs between vendors, by necessity](#what-differs-between-vendors-by-necessity): the page sizes, caches and prompts; and
7. [Every adapter: fetch, then parse](#every-adapter-fetch-then-parse): why an answer is saved before it is read.

## The two outputs, and how an adapter produces them

A page's tests read up to two outputs:

- `html`: the page transcribed, headers and footers kept; and
- `blocks`: layout blocks `{label, bbox, text}`, boxes from 0 to 1.

An adapter translates; it never edits, and no vendor is sent free-text instructions: each runs at
its own settings, with its documented options only. The vendor's text reaches the scorer as the
vendor wrote it, and anything that treats outputs differently (markers, tags, whitespace, look-alike
characters) belongs in the scorer, where it applies to every vendor alike. The only changes an
adapter makes are format changes, and each is checked to lose nothing:

- markdown goes through `markdown.to_html`; html is kept as it is;
- a vendor that returns its page header and footer beside the page rather than in it has them put
  back where they sit;
- a vendor's own markup is made plain html: Azure's header comments and Extend's own tags are
  unwrapped to their text, Extend's and Reducto r-1's figure descriptions become alt text,
  Mistral's table placeholders get their tables and its image placeholders are dropped, and a
  model's fenced reply is read from inside the fence;
- LlamaParse, Mistral and Azure record these changes in `sent` as `derived`, so the run states them;
  Extend's and Reducto's are listed here;
- blocks go through `layout.block` (the box in the vendor's frame, divided by the frame) and
  `layout.label` (the vendor's block type onto `views.LABELS`);
- a vendor with no typed layout doesn't support `blocks`, and those tests score unsupported for it
  rather than fail;
- every vendor gets the same retries: a transient failure (a rate limit, a 5xx, a dropped
  connection) is tried 4 times with backoff, within the same timeout per call. A model's reply that
  is cut off by an error or doesn't parse is asked again within the call, up to 3 times. A page a
  vendor still doesn't answer scores 0 on every test that reads the missing output, whatever the
  cause: answering is part of what a product does. A failure that is
  ours (an adapter that can't read an answer) counts as 0 like any other missing output until the
  adapter is fixed and `opb reparse` reads the answer again; and
- cost is what the response states, else `Cost()` (unknown). Credits go in `credits`, never
  converted to dollars.

Each vendor's request and response shapes below are from its documentation and are confirmed with
one live call per adapter (`opb predict --raw`) before a run.

## Block labels

A `layout_kind` test grades a block's label: the smallest block that covers at least half of a
line's place (`runners.holder`) must have the test's kind. So the labels are what is measured, and
the same kind of region must get the same label whatever the vendor calls it.

Each adapter has a `LABELS` table from the vendor's type to one of `views.LABELS`. A type not in it
fails the page's blocks with an error naming it, so a new type is decided here, never guessed. A
vendor with no type for a kind never gives it, and its tests of that kind fail. The LLM adapter is
the exception: a model's types are free text, so `layout.guess` reads them by the words in them.

The `form` label is a form field or a key-value pair (a label with its value), or a region of them.
Vendors draw it at different sizes: Datalab's `Form` is a whole form region, while Reducto's `Key
Value`, Extend's `key_value` and LlamaParse's `key-value-region` are a single key-value pair, which
also appears outside forms (an invoice's "Total: $5", a letterhead's "Tel: ..."). All of them map to
`form`. The label is not the `form` tag, which marks content that sits on a form.

Datalab (its `BLOCK_TYPES`; Diagram and ChemicalBlock reach the API as Figure, Bibliography as
ListGroup):

| Datalab type | label |
| --- | --- |
| Text, TableOfContents, Bibliography | text |
| SectionHeader | heading |
| PageHeader, PageFooter | page_furniture |
| ListGroup | list |
| Caption | caption |
| Footnote | footnote |
| Equation | equation |
| Code | code |
| Table | table |
| Form | form |
| Picture, Figure, Diagram, ChemicalBlock, ComplexRegion | figure |

ComplexRegion is a region of text and drawing together, seen on engineering and architectural
drawings; its text is mostly labels inside the drawing. TableOfContents is text, not a table.

Reducto (its documented `ParseBlock.type` list):

| Reducto type | label |
| --- | --- |
| Text, Comment | text |
| Title, Section Header | heading |
| Header, Footer, Page Number | page_furniture |
| List Item | list |
| Table | table |
| Key Value | form |
| Figure, Signature | figure |

Extend (its documented types; table_head and table_cell only with cell blocks on):

| Extend type | label |
| --- | --- |
| text | text |
| heading, section_heading | heading |
| header, footer, page_number | page_furniture |
| legend | caption |
| formula | equation |
| table, table_head, table_cell | table |
| key_value | form |
| figure, barcode | figure |

LlamaParse. A box's layout label decides, and a box with none takes its item's type. The layout
labels are free strings, not a documented list; these were seen in its answers on the benchmark's pages.

| LlamaParse box label | label |
| --- | --- |
| text, reference | text |
| paragraph_title, doc_title | heading |
| header, footer | page_furniture |
| list | list |
| caption | caption |
| footnote | footnote |
| formula | equation |
| code | code |
| table | table |
| key-value-region, form, checkbox-selected, checkbox-unselected | form |
| image, chart, seal | figure |

| LlamaParse item type (box without a label) | label |
| --- | --- |
| text, link | text |
| heading | heading |
| header, footer | page_furniture |
| list | list |
| code | code |
| table | table |
| image | figure |

Mistral (its documented block types):

| Mistral type | label |
| --- | --- |
| text, references, aside_text | text |
| title | heading |
| header, footer | page_furniture |
| list | list |
| caption | caption |
| equation | equation |
| code | code |
| table | table |
| image, signature | figure |

Azure (its documented paragraph roles; a paragraph with no role is body text, and tables and
figures are their own blocks):

| Azure role | label |
| --- | --- |
| (none) | text |
| title, sectionHeading | heading |
| pageHeader, pageFooter, pageNumber | page_furniture |
| footnote | footnote |
| formulaBlock | equation |
| table | table |
| figure | figure |

LightOn (the labels of its model card, and those its own ParseBench parser also reads; a label
ending in `+` continues the block before it and is read without the `+`):

| LightOn label | label |
| --- | --- |
| text, paragraph, aside_text | text |
| title | heading |
| header, footer, page_number, page_header, page_footer | page_furniture |
| list | list |
| caption, figure_title | caption |
| footnote, page_footnote | footnote |
| formula | equation |
| code | code |
| table | table |
| image, figure, chart, header_image, footer_image | figure |

## The vendors

| provider | API | outputs | headers | auth |
| --- | --- | --- | --- | --- |
| `datalab` | /api/v1/convert | html, blocks | native switch, set to keep them | DATALAB_API_KEY |
| model ids (GPT, Claude, ...) | OpenRouter chat | html, blocks | its prompt asks to keep them | OPENROUTER_API_KEY (or OPENAI_API_KEY) |
| `reducto` | /upload, /parse_async, /job | html, blocks | kept in its content | REDUCTO_API_KEY |
| `extend` | /files/upload, /parse_runs | html, blocks | kept in its content | EXTEND_API_KEY (and EXTEND_WORKSPACE_ID when the key spans several workspaces) |
| `llamaparse` | /api/v2/parse/upload, poll, expand=markdown,items,usage | html, blocks | header and footer fields beside the markdown, put back | LLAMA_CLOUD_API_KEY |
| `azure` | Content Understanding, prebuilt-layout | html, blocks | comments in its markdown, unwrapped | AZURE_CU_KEY, and the `endpoint` option |
| `mistral` | /v1/ocr (mistral-ocr-4-1) | html, blocks | header and footer fields beside the markdown, put back | MISTRAL_API_KEY |
| a served open-weight model (see Open-weight models) | its oss/ server: vLLM, or the vendor's code around it, on any GPU host | html, blocks (olmOCR-2, Nanonets-OCR2: html) | kept: vendor defaults that leave them out turned off | OPB_ENDPOINT_KEY, when the server has one |
| `tesseract` | the local `tesseract` binary, no model of the page | html | kept: it has no notion of them | none |

A vendor's tiers are runs of their own: `--options '{"datalab": [{"mode": "balanced"}, {"mode":
"accurate"}], "llamaparse": [{"tier": "agentic"}, {"tier": "agentic_plus"}]}'` makes four runs in one
invocation. `opb providers` lists each vendor's options. Any OpenRouter model id works
(`openai/gpt-5.6-sol`, ...).

Per vendor:

- datalab: one `/api/v1/convert` call at `mode=accurate`, its most accurate, with
  `output_format=html,chunks`, cache skipped (`skip_cache`), page headers and footers kept
  (`keep_pageheader_in_output`, `keep_pagefooter_in_output`), image extraction and captions off,
  polled. Blocks are its chunks, with boxes in the page's frame. Cost: stated in cents, recorded in
  dollars;
- models (any OpenRouter id): one chat call per output, each with its own prompt, the page as a PNG
  at high detail, no sampling settings sent. Cost: OpenRouter's `usage.cost` in dollars (plus
  `cost_details.upstream_inference_cost` under BYOK), with tokens;
- reducto: upload the page, then `/parse_async` on r-1, its newest model (`settings.model`; without
  it Reducto runs its legacy pipeline), with tables as html and chunking off, polled. r-1 does the
  legacy agentic passes itself, so they are sent only with `model` legacy (tables at `max`, text
  on). Each block has a `type`, a normalized `bbox` (left, top, width, height) and `content`. html is
  the page content as Reducto returns it, with r-1's figure descriptions as alt text; blocks are the
  blocks. Cost: stated in its credits;
- extend: upload, then a parse run (`parse_performance`, its most accurate engine), polled, with
  its agentic passes on (text and tables, each off by default) and an image converted to PDF at
  high quality (`imageConversionQuality`, default medium). A run that fails with `INTERNAL_ERROR`
  or `OCR_ERROR`, an outage of Extend's, is retried as a 5xx is; another failure reason is the
  file's, and final. Its page content is its blocks joined. Its figure model writes a description
  of each figure as a `<caption>` inside the `<figure>`, with no switch to turn off only that, so
  the description becomes the image's alt text, where every vendor's image descriptions go and the
  scorer treats them alike. Its own tags (`<page_number>`) are unwrapped to their text. Boxes are
  in the page's pixels, with the page size on each block. Cost: stated in its credits;
- llamaparse: the v2 API at `agentic_plus`, its most accurate tier. Its page markdown leaves out
  what it classed as page header and footer and returns them in the page's `header` and `footer`
  fields, so html is header, markdown and footer joined. Blocks are its items' boxes,
  each with a layout label and the span of the item's text it covers, read at every level of the
  item tree (a list's items, a header's lines). Cost: stated in its credits;
- azure: analyze with the prebuilt layout analyzer (api 2025-11-01), at the resource given as the
  `endpoint` option (a setting, so it is in the run's settings and name). Its markdown renders tables
  as html and writes page headers, footers and page numbers in place as comments
  (`<!-- PageHeader: ... -->`), which html unwraps into their text. Blocks are its paragraphs
  (with their `role`), tables and figures, from `source` boxes in the page's unit. Cost: unknown (it
  states pages used);
- mistral: one POST to `/v1/ocr` with the page inline, tables asked for as html, header and footer
  extracted, blocks on and image data not returned (their placeholders are
  dropped; their regions stay in the blocks). Its page markdown leaves tables as placeholders
  (`[tbl-0.html]`) whose html is beside it, and moves header and footer into their own fields, so
  html is header, markdown and footer joined, tables put in place. Blocks are its paragraph blocks,
  typed, with boxes in the page's pixels. Cost: unknown (it states pages processed); and
- tesseract: the floor, plain OCR with no model of the page beyond its characters, run locally at no
  cost. A PDF page is rendered at 300 dpi (pypdfium2); Tesseract detects the page's script itself
  (`--psm 0`) and reads it with that script's model, English when it detects none it has a model
  for, so it is told nothing about the page. Its text is written as html inside `<pre>`, escaped,
  and it gives no layout blocks. Needs `brew install tesseract tesseract-lang` (or the
  distribution's tesseract and its script models).

## Serving an open model

Serving and benchmarking are separate. Each open model has a folder, `omni_parse_bench/harness/providers/oss/<model>/`,
that deploys it on any GPU host, and opb then benchmarks it from anywhere, pointed at its URL:

    docker build -t opb-dots omni_parse_bench/harness/providers/oss/dots
    docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-dots
    opb benchmark --providers dots-mocr --options '{"dots-mocr": {"base_url": "http://<host>:8001"}}'

A folder holds:

- `Dockerfile`: the vendor's environment, pinned (base image, packages, repository at a commit);
- `start.sh`: vLLM with the vendor's flags and the weights at a pinned revision, then server.py if
  there is one; one port out, 8001; and
- `server.py`, for a model whose vendor's code takes part in reading a page (loading the file,
  preparing the image, asking, retrying, its pipeline or post-processing): that code, per page,
  behind one route, taking the page file and answering with the vendor's output and the model's raw
  reply.

A server.py stands alone: it imports its vendor's code and what that needs, never omni_parse_bench,
and nothing in omni_parse_bench imports it. So the vendor's code (and its license) stays in its image,
and the adapter that reads the answer needs none of it: a saved answer is read again anywhere.

A model whose vendor offers only the model, with no code of its own around it (Nanonets-OCR2), has no
server.py: its port is vLLM's `/v1`, and its adapter asks it directly, through `llm.chat`.

OPB_ENDPOINT_KEY, when the server has it, is required as the bearer token, and opb sends it to any
endpoint but OpenRouter's. A page can take minutes (a vendor's retries, a looping reply), so a server
must hold a request open as long as the call's 900 s, with no proxy in front that cuts requests sooner.
Run opb beside the server, on the same host or network: every page file is sent to it, and many pages
at once over a slow link wait on time the 900 s counts against the model. Send a server no more pages at
once than it reads at once, for the same reason.

## Open-weight models

Each model runs with the defaults its vendor recommends; each adapter's docstring lists where it differs.

| model | provider | oss/ | outputs |
| --- | --- | --- | --- |
| LightOnOCR-3 (4B, 0.8B) | `lightonocr` (`model`) | `lighton` | html, blocks |
| dots.mocr | `dots-mocr` | `dots` | html, blocks |
| Unlimited-OCR | `unlimited-ocr` | `unlimited` | html, blocks |
| Infinity-Parser2 (Pro, Flash) | `infinity-parser2` (`model`) | `infinity` | html, blocks |
| chandra-ocr-2 | `chandra-ocr` | `chandra` | html, blocks |
| olmOCR-2 | `olmocr` | `olmocr` | html |
| HunyuanOCR-1.5 | `hunyuan-ocr` | `hunyuan` | html, blocks |
| DeepSeek-OCR-2 | `deepseek-ocr` | `deepseek` | html, blocks |
| Surya OCR 2 | `surya-ocr` | `surya` | html, blocks |
| MinerU2.5-Pro | `mineru` | `mineru` | html, blocks |
| GLM-OCR | `glm-ocr` | `glm_ocr` | html, blocks |
| PaddleOCR-VL-1.6 | `paddleocr-vl` | `paddleocr_vl` | html, blocks |
| Nanonets-OCR2-3B | `nanonets-ocr` | `nanonets` | html |

olmOCR-2 and Nanonets-OCR2 return no layout, so they have no blocks.

Their labels (LightOn's table is above):

chandra-ocr-2 (`providers/chandra_ocr.py`):

| chandra-ocr-2 label | label |
| --- | --- |
| Text, Table-Of-Contents, Bibliography | text |
| Section-Header | heading |
| Page-Header, Page-Footer | page_furniture |
| List-Group | list |
| Caption | caption |
| Footnote | footnote |
| Equation-Block | equation |
| Code-Block | code |
| Table | table |
| Form | form |
| Image, Figure, Picture, Diagram, Chemical-Block, Complex-Block | figure |

dots.mocr (`providers/dots.py`):

| dots.mocr label | label |
| --- | --- |
| Text | text |
| Title, Section-header | heading |
| Page-header, Page-footer | page_furniture |
| List-item | list |
| Caption | caption |
| Footnote | footnote |
| Formula | equation |
| Table | table |
| Picture | figure |

Unlimited-OCR (`providers/unlimited.py`):

| Unlimited-OCR label | label |
| --- | --- |
| text, aside_text, ref_text | text |
| title, sub_title | heading |
| header, footer, page_number | page_furniture |
| list | list |
| image_caption, table_caption, caption | caption |
| footnote, table_footnote, image_footnote, page_footnote | footnote |
| equation | equation |
| code, algorithm | code |
| table | table |
| image, chart | figure |

Infinity-Parser2 (`providers/infinity.py`):

| Infinity-Parser2 label | label |
| --- | --- |
| text | text |
| title | heading |
| header, footer | page_furniture |
| figure_caption, table_caption, formula_caption, table_text | caption |
| figure_footnote, table_footnote, page_footnote | footnote |
| formula | equation |
| table | table |
| form, label | form |
| figure, signature | figure |

MinerU2.5-Pro (`providers/mineru.py`):

| MinerU2.5-Pro label | label |
| --- | --- |
| text, aside_text, ref_text, index, phonetic, unknown | text |
| title, doc_title, paragraph_title | heading |
| header, footer, page_number | page_furniture |
| list, list_item | list |
| caption, table_caption, image_caption, code_caption | caption |
| footnote, table_footnote, image_footnote, page_footnote | footnote |
| equation, equation_block, formula_number | equation |
| code, algorithm | code |
| table | table |
| image, chart, image_block | figure |

GLM-OCR (`providers/glm_ocr.py`):

| GLM-OCR label | label |
| --- | --- |
| text, abstract, content, reference_content, reference, vertical_text, aside_text | text |
| doc_title, paragraph_title | heading |
| header, footer, number | page_furniture |
| figure_title | caption |
| footnote, vision_footnote | footnote |
| display_formula, inline_formula, formula_number | equation |
| algorithm | code |
| table | table |
| image, chart, seal, header_image, footer_image | figure |

PaddleOCR-VL-1.6 (`providers/paddleocr_vl.py`):

| PaddleOCR-VL-1.6 label | label |
| --- | --- |
| text, abstract, content, reference, reference_content, aside_text, vertical_text | text |
| paragraph_title, doc_title | heading |
| header, footer, number | page_furniture |
| figure_title | caption |
| footnote, vision_footnote | footnote |
| display_formula, inline_formula, formula_number | equation |
| algorithm | code |
| table | table |
| image, chart, seal, header_image, footer_image | figure |

DeepSeek-OCR-2 (`providers/deepseek_ocr.py`):

| DeepSeek-OCR-2 label | label |
| --- | --- |
| text, aside_text, ref_text | text |
| title, sub_title | heading |
| header, footer, page_number | page_furniture |
| list | list |
| image_caption, table_caption, caption, figure_title | caption |
| footnote, table_footnote, image_footnote, page_footnote | footnote |
| equation, formula_number | equation |
| code, algorithm | code |
| table | table |
| image, chart | figure |

HunyuanOCR (`providers/hunyuan.py`):

| HunyuanOCR label | label |
| --- | --- |
| paragraph, paragraph_span, para, text, abstract, reference, aside_text, table_of_contents, content, none, partial_para | text |
| doc_title, title, para_title, section_title, sub_title, heading | heading |
| header, footer, page, page_number, page_header, page_footer, watermark | page_furniture |
| list, list_item | list |
| figure_title, table_title, chart_title, caption, figure_caption, table_caption, table_header_note, table_both | caption |
| footnote, table_footnote, page_footnote, figure_footnote, table_footer_note | footnote |
| formula, equation, formula_number | equation |
| code, algorithm | code |
| table | table |
| checkbox, check, box, radio_button, radio_button_span, form | form |
| figure, chart, image, seal, stamp, signature, algorithm_chart | figure |

Surya OCR 2 (`providers/surya_ocr.py`):

| Surya OCR 2 label | label |
| --- | --- |
| Text, TableOfContents, Bibliography | text |
| SectionHeader | heading |
| PageHeader, PageFooter | page_furniture |
| ListGroup | list |
| Caption | caption |
| Footnote | footnote |
| Equation | equation |
| Code | code |
| Table | table |
| Form | form |
| Picture, Figure, Diagram, ChemicalBlock | figure |

## What differs between vendors, by necessity

- The models get the page as a PNG, a PDF rendered with pdfium or an image shrunk, at most 2048 px
  on its long edge (about 186 DPI for a letter page); the vendors get the original file
  (Tesseract, run locally, a 300 dpi render);
- Datalab and LlamaParse are told not to answer from a cache (`skip_cache`, `disable_cache`); the
  others have no such switch or don't document one. Without it, LlamaParse returns its earlier job
  for a file it has seen, so neither the output nor the time would be this run's; and
- the models' prompts say what to write (a page's text as HTML, checkboxes as glyphs, math as
  LaTeX); a vendor is asked for its format with its options only. A prompt is the model's input, so
  this is the fair equivalent of a vendor's settings, and every prompt is in `llm.py` and its digest
  in the run's name.

## Every adapter: fetch, then parse

`call` returns the vendor's answer as received, and `parse` reads the outputs from it. Every answer
is saved in the run's records (`raw`), even when parsing it fails, and a paid failure keeps its
answer, cost and job id. So a parsing fix reaches a finished run with `opb reparse RUN_DIR`, and
never needs the vendor again. `--retry-failed` predicts again only the outputs whose failure may
not recur: a timeout, an outage, a 429 or 5xx, or no HTTP status; never a 400 or a vendor's answer.
