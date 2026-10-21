"""A PDF page as an image (`render`), for systems that take pixels. Every render in the process holds one
lock, since pdfium isn't thread-safe and adapters run on many threads.
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
