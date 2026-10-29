# Providers

How each vendor becomes an adapter in `omni_parse_bench/harness/providers/`: one module per vendor,
each defining one `Parser` class (`harness/adapter.py`), the omni-bench-core core's `Adapter` for one
page. The class has:

- its fields: the vendor's options;
- `SUPPORTS`: the output types it can produce;
- `keys`: the environment variables it needs, such as its API key, checked before any call; `ENV`
  says in words what else the environment can hold for it (an optional bearer token); and `SERVE`, for
  a model you serve, names its folder in `providers/serve/`;
- `requests(wants)`: the calls a page needs, for the outputs it wants that the adapter supports; it is
  never given an empty set;
- `send(page, request, *, timeout)`: make one call and return the vendor's answer as received, with
  its cost. It is called from `workers` threads at once, one page each, so a library that isn't
  thread-safe needs a lock: pdfium is one, so render pages with `raster`, which holds its lock; and
- `parse(raw, request)`: read the outputs from an answer.

`Parser` turns these into the core's `call` and `read`: `call` makes every request for a page
within the page's one time budget and keeps each answer, and `read` parses each saved answer.
`registry.ADAPTERS` lists the vendors and the open-weight models with adapters of their own; any
model id goes to `llm.LLM`.

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
- a vendor with no typed layout doesn't support `blocks`. It is never asked for them: a page asks it
  only for html, and a page whose tests read blocks alone is not sent. Its blocks tests fail as "no
  blocks output", so its layout family is 0 and its text and tables families say how it reads;
- every vendor gets the same retries: a transient failure (a rate limit, a 5xx) is tried 4 times with
  backoff, the whole page again, within the same time per page. A transport failure (a connection, a
  read, a client timeout) of any request (an upload, a submit, a poll, once a poll's own retries are
  spent) is the page's failure, `SystemUnreachable` or `SystemTimeout`, which a page asks again only
  under `--retry-failed`; its record's traceback shows the httpx error underneath. A refused connection
  stops the run instead. A model's reply that is cut off by an error or doesn't parse is asked again within the call, up to 3
  times. A page a vendor still doesn't answer fails, every test failed, whatever the cause: answering is part of
  what a product does. Under the core's one rule ([omni-bench-core's "The rules"](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules)),
  a page fails only when the adapter raises `SystemFailed` on purpose, or reads the answer inside
  `omni_bench_core.adapter.reading`, which raises it for a malformed one. The record keeps the failure
  with its `traceback`. Any other exception is the adapter's bug, not the vendor's:
  - a bug in `parse` stops the run with its traceback; the raw answer is kept, unread (`"unread":
    true`), and resuming the run (`opb resume`) after the fix reads it with no call; and
  - a bug elsewhere in the adapter stops the run too, printing its whole traceback and whose code it
    is; and
- cost is what the response states, else `Cost()` (unknown). Credits go in `credits`, never
  converted to dollars.

Each vendor's request and response shapes below are from its documentation and are confirmed with
one live call per adapter (`opb predict --system <name> --page <file> --raw`) before a run.

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

Datalab (its block types; Diagram and ChemicalBlock reach the API as Figure, Bibliography as
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

Each system's environment variables are in the last column, and `opb systems NAME` prints them. A key
that is missing stops a run before any call and says which `export` to type.

| provider | API | outputs | headers | auth (environment variables) |
| --- | --- | --- | --- | --- |
| `datalab` | /api/v1/convert | html, markdown, blocks | native switch, set to keep them (`headers_footers`) | DATALAB_API_KEY |
| model ids (GPT, Claude, ...) | OpenRouter chat | html, blocks | its prompt asks to keep them | OPENROUTER_API_KEY (or OPENAI_API_KEY) |
| `reducto` | /upload, /parse_async, /job | html, blocks | kept in its content | REDUCTO_API_KEY |
| `extend` | /files/upload, /parse_runs | html, blocks | kept in its content | EXTEND_API_KEY (and EXTEND_WORKSPACE_ID when the key spans several workspaces) |
| `llamaparse` | /api/v2/parse/upload, poll, expand=markdown,items,usage | html, blocks | header and footer fields beside the markdown, put back | LLAMA_CLOUD_API_KEY |
| `azure` | Content Understanding, prebuilt-layout | html, blocks | comments in its markdown, unwrapped | AZURE_CU_KEY, and the `endpoint` option |
| `mistral` | /v1/ocr (mistral-ocr-4-1) | html, blocks | header and footer fields beside the markdown, put back | MISTRAL_API_KEY |
| a served open-weight model (see Open-weight models) | its serve/ server: vLLM, or the vendor's code around it, on any GPU host | html, blocks (olmOCR-2, Nanonets-OCR2: html) | kept: vendor defaults that leave them out turned off | none; OPB_ENDPOINT_KEY, when the server has one |
| `tesseract` | the local `tesseract` binary, no model of the page | html | kept: it has no notion of them | none |

A vendor's tiers are runs of their own, one config each (or one config and `--set`), with the same pages:

    opb init datalab > datalab.yaml
    opb run --config datalab.yaml --set system.datalab.mode=balanced --set rows.sample=20
    opb run --config datalab.yaml --set system.datalab.mode=accurate --set rows.sample=20

`opb systems` lists each vendor's options. Any OpenRouter model id works (`openai/gpt-5.6-sol`, ...).

Per vendor:

- datalab: one `/api/v1/convert` call at `mode=accurate`, its most accurate, with
  `output_format=html,markdown,chunks` (those the page asks for), cache skipped (`skip_cache`), page
  headers and footers kept (`keep_pageheader_in_output`, `keep_pagefooter_in_output`; the option
  `headers_footers: false` leaves them out, the API's default), image extraction and captions off,
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
  and it gives no layout blocks. It is free, so its cost is recorded as `usd` 0.0. A tesseract that
  exits with an error fails the page as a `SystemFailed` with its stderr. Needs `brew install tesseract tesseract-lang` (or the
  distribution's tesseract and its script models).

## Serving an open model

Serving and benchmarking are separate. Each open model has a folder, `omni_parse_bench/harness/providers/serve/<model>/`,
that deploys it on any GPU host, and opb then benchmarks it from anywhere, pointed at its URL:

    docker build -t opb-dots-mocr omni_parse_bench/harness/providers/serve/dots-mocr
    docker run --gpus all -p 8001:8001 -v ~/.cache/huggingface:/root/.cache/huggingface opb-dots-mocr
    opb init dots-mocr > dots.yaml
    opb run --config dots.yaml --set system.dots-mocr.base_url=http://<host>:8001

Which model answers is part of the run: the system's `served` option names the weights and their revision
(`opb init` writes the folder's defaults), so another checkpoint is another run. Before any call, opb asks the
server what it serves (its `/served` route; a vLLM alone, its `/v1/models`) and refuses a run whose server
serves something else, so a run folder always names the weights that answered. To serve other weights, start
the folder with `WEIGHTS` and `REVISION` and give the same in `served`.

If nothing listens at `base_url` (the server isn't started, or the address is wrong), the connection is
refused and the run stops before recording anything, with a message naming the address and the model's
folder here. Start the server, or fix the address, and resume the run (`opb resume`). A server that is up
but slow is different: a page it doesn't answer in time is recorded as a timeout, which fails the page and is
tried again with `opb resume <its folder> --retry-failed`.

A folder holds:

- `Dockerfile`: the vendor's environment, pinned: the base image by digest, every Python package by
  version, the vendor's repository at a full commit. apt packages aren't pinned: `poppler-utils` (LightOn,
  olmOCR), `libcairo2` (dots.mocr) and olmOCR's fonts come from the base image's Ubuntu release when the
  image is built, so a later build may get newer ones, which can change how a page is rendered;
- `start.sh`: vLLM with the vendor's flags and the weights WEIGHTS and REVISION name, by default the
  pinned ones opb's numbers come from (`docker run -e WEIGHTS=... -e REVISION=...` serves others), then
  server.py if there is one; one port out, 8001; and
- `server.py`, for a model whose vendor's code takes part in reading a page (loading the file,
  preparing the image, asking, retrying, its pipeline or post-processing): that code, per page,
  behind one route, taking the page file and answering with the vendor's output and the model's raw
  reply.

A server.py stands alone: it imports its vendor's code and what that needs, never omni_parse_bench,
and nothing in omni_parse_bench imports it. So the vendor's code (and its license) stays in its image,
and the adapter that reads the answer needs none of it: a saved answer is read again anywhere.

A server.py takes exactly its `SETTINGS` and refuses any other. Its adapter sends them as its options
(`http.settings`): every option but `base_url`, `model`, `served`, and one the adapter applies itself,
which its field marks `metadata={"local": True}` (hunyuan's `long_edge`, chandra-ocr's
`headers_footers`). A test checks that each adapter sends exactly its server's `SETTINGS`.

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
Two differences hold for every model, and aren't repeated there: each page has the benchmark's 900 s,
and a picture's contents (a description, a chart's data) become an image's alt text.

| model | provider | serve/ | outputs |
| --- | --- | --- | --- |
| LightOnOCR-3 (4B, 0.8B) | `lightonocr` | `lightonocr` | html, blocks |
| dots.mocr | `dots-mocr` | `dots-mocr` | html, blocks |
| Unlimited-OCR | `unlimited-ocr` | `unlimited-ocr` | html, blocks |
| Unlimited-OCR 2 | `unlimited-ocr-2` | `unlimited-ocr-2` | html, blocks |
| Infinity-Parser2 (Pro, Flash) | `infinity-parser2` | `infinity-parser2` | html, blocks |
| chandra-ocr-2 | `chandra-ocr` | `chandra-ocr` | html, markdown, blocks |
| olmOCR-2 | `olmocr` | `olmocr` | html |
| HunyuanOCR-1.5 | `hunyuan-ocr` | `hunyuan-ocr` | html, blocks |
| DeepSeek-OCR-2 | `deepseek-ocr` | `deepseek-ocr` | html, blocks |
| Surya OCR 2 | `surya-ocr` | `surya-ocr` | html, blocks |
| MinerU2.5-Pro | `mineru` | `mineru` | html, blocks |
| GLM-OCR | `glm-ocr` | `glm-ocr` | html, blocks |
| PaddleOCR-VL-1.6 | `paddleocr-vl` | `paddleocr-vl` | html, blocks |
| Indra OCR | `indra-ocr` | `indra-ocr` | html, blocks |
| Nanonets-OCR2-3B | `nanonets-ocr` | `nanonets-ocr` | html |
| Nemotron 3.5 Parse | `nemotron-parse` | `nemotron-parse` | html, blocks |
| MiniCPM-OCR 1.0 | `minicpm-ocr` | `minicpm-ocr` | html, markdown, blocks |
| OXR-1.0 | `oxr` | `oxr` | html, markdown, blocks |

olmOCR-2 and Nanonets-OCR2 return no layout, so they have no blocks. Indra OCR runs on CPU (ONNX Runtime),
no GPU: its server reads pages in one worker process per core, and its image runs without `--gpus`.

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

Unlimited-OCR 2 (`providers/unlimited_ocr2.py`): Unlimited-OCR's labels, with a `cross_` or `append_` prefix
(a block continued across pages or columns) dropped, and:

| Unlimited-OCR 2 label | label |
| --- | --- |
| figure, picture, seal | figure |
| other | text |

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

Indra OCR (`providers/indra_ocr.py`):

| Indra OCR label | label |
| --- | --- |
| Text, Table-Of-Contents | text |
| Section-Header | heading |
| Page-Header, Page-Footer | page_furniture |
| List-Group | list |
| Caption | caption |
| Footnote | footnote |
| Table | table |
| Form | form |

Nemotron 3.5 Parse (`providers/nemotron_parse.py`; its class tokens, and Chart):

| Nemotron 3.5 Parse class | label |
| --- | --- |
| Text, TOC, Bibliography | text |
| Title, Section-header | heading |
| Page-header, Page-footer | page_furniture |
| List-item | list |
| Caption | caption |
| Footnote | footnote |
| Formula | equation |
| Code | code |
| Table | table |
| Picture, Chart | figure |

MiniCPM-OCR 1.0 (`providers/minicpm_ocr.py`):

| MiniCPM-OCR 1.0 label | label |
| --- | --- |
| abstract, content, reference, reference_content, text, vertical_text, aside_text | text |
| doc_title, paragraph_title | heading |
| header, footer, number | page_furniture |
| figure_title | caption |
| footnote, vision_footnote | footnote |
| display_formula, inline_formula, formula_number | equation |
| algorithm | code |
| table | table |
| chart, seal, image, header_image, footer_image | figure |

OXR-1.0 (`providers/oxr.py`; the types of SoMark's API, `oxr/pipeline/models.py`):

| OXR-1.0 label | label |
| --- | --- |
| Text | text |
| Title | heading |
| Page-header, Page-footer | page_furniture |
| Caption | caption |
| Footnote | footnote |
| Formula, Chemical Equation | equation |
| Code Block | code |
| Table | table |
| Picture, Stamp, Chemical Structure | figure |

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

`send` returns the vendor's answer as received, and `parse` reads the outputs from it. Every answer
is saved in the run's records (`raw`), even when parsing it fails. `parse` says on purpose when an
answer is the vendor's failure, and every adapter writes it the same way:

- an answer that holds no usable page (no chunks, no markdown, a page the vendor marked failed, a reply
  that didn't finish) raises `SystemFailed` with a message saying what was missing;
- the vendor's own structures (a job's chunks, a page's markdown) are read inside `adapter.reading`, so
  a malformed one is the vendor's failure too;
- in either case the page is recorded as `Unreadable`, which fails the page and keeps the message and its
  traceback, so the record says what couldn't be read; it is never scored as an empty page;
- `blocks` are read apart from the page, inside `reading` within a `try` that leaves them out: a
  malformed block, or a block type the adapter's `LABELS` lacks, fails the page's blocks output only;
  its html is still graded. A key missing from our own model server's answer (`completion`, `text`,
  `markdown`, `blocks`) is a bug, not a malformed block; and
- anything else `parse` raises is a bug in it: the run stops, the answer is kept unread, and the same
  command reads it again after the fix.

A fix to a `parse` that gave wrong outputs without raising reaches a finished run with `opb reread
RUN_DIR` (`Benchmark.reread(folder, system)`), and never needs the vendor again; grade the run again
afterwards. What happens in every other case is
omni-bench-core's rules ([the table](https://github.com/datalab-to/omni-bench-core/blob/main/OVERVIEW.md#the-rules)). `--retry-failed` predicts again only
the pages whose failure may not recur: a timeout, an outage, a 429 or 5xx; never a 400 or a vendor's
answer.
