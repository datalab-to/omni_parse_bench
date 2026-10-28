# MiniCPM-OCR 1.0

The official MiniCPM-OCR SDK parses each page with PP-DocLayoutV3 and the 1.3B recognition model.
The SDK runs in its own Python environment, with CPU layout detection; vLLM serves BF16 recognition
on the GPU. The upstream SDK, Transformers and vLLM sources are pinned by commit. The SDK verifies
the layout archive's SHA256. The recognition weights are pinned in `start.sh` and the adapter.

```bash
docker build -t opb-minicpm-ocr omni_parse_bench/harness/providers/serve/minicpm-ocr
docker run --gpus all -p 8001:8001 \
    -v ~/.cache/huggingface:/root/.cache/huggingface opb-minicpm-ocr
opb init minicpm-ocr > minicpm.yaml
opb run --config minicpm.yaml --set rows.sample=5
```

Use a Linux x86_64 NVIDIA host. The pinned upstream recipe builds vLLM from source, so the first
image build is substantial (upstream estimates about 40 minutes on a 96-core machine). Its CUDA 13
runtime requires a compatible driver; on older drivers follow upstream's compatibility-library
instructions for that host. A laptop can run OPB against `system.minicpm-ocr.base_url=http://HOST:8001`.

Set `OPB_ENDPOINT_KEY` in the container and OPB client to require a bearer token. `WEIGHTS` and
`REVISION` select another checkpoint; set the adapter's `served` to the same values. The layout
model is cached beneath `HF_HOME`, beside the recognition weights.

PDFs use the SDK's PyMuPDF render at 144 DPI. The SDK's region prompts, sampling, table conversion,
formula repair and repetition handling are retained. Markdown keeps every label, including the
headers, footers, numbers, footnotes and aside text the vendor normally omits. DSpark, orientation
correction, cross-page table merging and test-time selection are disabled. The result includes native
Markdown and structured blocks with raw recognition text, statuses and the SDK summary. Partial
region failures retain the SDK's partial output; a missing page result fails the page.
Native Markdown includes chart/seal recognition as the SDK emits it; the HTML view expresses those
contents as image alt text, as OPB does for other systems' picture contents.

Four uvicorn workers each keep one SDK layout detector and recognition client loaded, using the
SDK's `pipelined_run(..., resources=...)` API. Each worker handles one page at a time, with 32 concurrent
region recognition requests within it. OPB sends four pages at once by default, matching the four
pipelines, as in the PaddleOCR-VL server. A page's HTTP call has the benchmark's time budget; it does
not start a new SDK process or load a new layout model for every page.

Sources: [SDK tutorial](https://github.com/OpenBMB/MiniCPM-OCR/blob/d9de88090765c2895c5ca192699da099f79e3fed/docs/minicpmvocr_tutorial_en.md),
[SDK source](https://github.com/OpenBMB/MiniCPM-OCR/tree/d9de88090765c2895c5ca192699da099f79e3fed/sdk),
[runtime pins](https://github.com/OpenBMB/MiniCPM-OCR/blob/d9de88090765c2895c5ca192699da099f79e3fed/pyproject.toml).
