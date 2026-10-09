"""A PDF page as an image, for the providers that send or read pixels instead of the PDF.

pdfium isn't thread-safe, and a benchmark calls providers from many threads at once, several
providers in one run; so every render in the process goes through one lock, here.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PIL import Image

# Note: concurrent pdfium calls fail at random ("Failed to load document (PDFium: Success)") or abort.
_LOCK = threading.Lock()


def render(pdf: Path, scale: Callable[[tuple[float, float]], float]) -> Image.Image:
    """The PDF's first page, at `scale(size)` pixels per point, `size` its (width, height) in points."""
    import pypdfium2 as pdfium

    with _LOCK:
        doc = pdfium.PdfDocument(pdf)
        try:
            page = doc[0]
            bitmap = page.render(scale=scale(page.get_size()))
            try: return bitmap.to_pil()
            finally: bitmap.close()
        finally:
            doc.close()
