# Run notes for open tools run locally

These full runs use the public dataset (2,937 pages) and released omni-parse-bench 1.7.0, graded without `--partial`; failed pages count as failures. Dataset commits, run IDs, settings, retries and coverage are recorded where reported in the source PRs or README.

## pdftotext

- Dataset: Hugging Face `datalab-to/omni_parse_bench` at `1045c42`; 2,937 pages.
- Run: Full public run; run folder not named in the merged PR. The reported 5-page CPU smoke run is separate.
- Settings: Poppler `pdftotext page.pdf -` defaults (reading order, no `-layout`); text escaped in `<pre>`. No OCR engine.
- Outcome: 0 failed pages; 100% coverage; about 20 seconds on laptop CPU. No retries reported.
- Notes: Reads only the PDF text layer, so image pages and scans without embedded text return empty output.

## pdftext

- Dataset: Hugging Face `datalab-to/omni_parse_bench`; 2,937 pages.
- Run: `pdftext-20261125-233108-3259`.
- Settings: `pdftext` 0.7.1, README plain-text defaults (`sort=False`, `hyphens=False`); text escaped in `<pre>`. No OCR engine.
- Outcome: 0 failed pages; 100% coverage; about one minute CPU wall time. No retries reported.
- Notes: Reads only the PDF text layer; scans without embedded text return empty output.

## MarkItDown

- Dataset: Hugging Face `datalab-to/omni_parse_bench`; 2,937 pages.
- Run: `markitdown-20261125-233224-6ae7`.
- Settings: MarkItDown 0.1.9 at documented defaults; Markdown returned as HTML. No OCR engine.
- Outcome: 3 system failures, 2,934 pages with predictions; 99.9% coverage; about 8 minutes CPU wall time. `opb resume --retry-failed` found no retryable pages; a fresh CPU run of the three failed pages also failed.
- Failures: `PDFKeyError` because a PDF stream lacks attribute `N`, on `olmo_multi_column-0845863d27c84b14011e17a388821525e783_page_12_pg1-p1` (object 72), `..._page_16_pg1-p1` (object 53) and `..._page_4_pg1-p1` (object 92). Released 1.7.0 grading counts their tests as failed system pages.

## pdf-inspector

- Dataset: Public dataset at commit `24e3ef4d2aa1718e622d357db7f6d0d10742c93`; 2,937 pages.
- Runs: Text `pdf-inspector-20261126-014930-77ac`; OCR `pdf-inspector-ocr-20261126-014924-02a9`. Two image-conversion failures in each full run were retried after Pillow decoded and losslessly rewrote the pages as canonical PNGs: text `pdf-inspector-20261126-015509-6e6d`; OCR `pdf-inspector-ocr-20261126-020636-7886` and `pdf-inspector-ocr-20261126-020705-a3dc`.
- Settings: Text and OCR modes. OCR used PDFium `native-v7988`, ONNX Runtime 1.27.0 and the documented PP-OCRv6 Small model set (~31 MB), with `PDFIUM_LIB_PATH` and `ORT_DYLIB_PATH` set.
- Outcome: Merged full-run outputs: 0 failed pages; 100% coverage. No additional retries reported.

## PyMuPDF4LLM

- Dataset: Public dataset at commit `24e3ef4d2aa1718e622d357db7f6d0d10742c93`; 2,937 pages.
- Runs: Text `pymupdf4llm-20261126-041521-4291`; OCR `pymupdf4llm-ocr-20261126-044854-b1b7`.
- Settings: Default mode and OCR mode. OCR used Tesseract (available); RapidOCR was not installed.
- Outcome: Both saved runs were reread with `opb reread` (0 changed records) and graded with released 1.7.0. Each had 17 system failures and 2,920/2,937 scored pages (99.42% coverage); 14 image pages failed with `FzErrorFormat: unknown image file format`, and 3 pages failed when PyMuPDF's layout model read form widgets.
