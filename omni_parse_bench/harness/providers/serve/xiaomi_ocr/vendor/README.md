Xiaomi-OCR-0 post-processing, Apache-2.0.

Source: https://github.com/SeerRay-Lab/Xiaomi-OCR-0/tree/b1a9bb4c07060c453785e9151715ccda6b96f0b1/postprocess

`document.py` and `otsl.py` are copied from that revision. The sole source change
is the relative import in `document.py`. The upstream license is included.
`finalize_document` trims repeated tails, normalizes math delimiters, and converts
OTSL table blocks to HTML, as the vendor whole-page pipeline does.
