"""PDF pages for systems: one page as an image (`render`), for systems that take pixels, and a document as
its pages (`pages`), one file each. Every pdfium call in the process holds one lock, since pdfium isn't
thread-safe and adapters run on many threads.
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
    """The PDF's page, at `scale(size)` pixels per point, `size` its (width, height) in points. Refuses a PDF
    of more than one page, which a page's adapter would otherwise read as its first page alone."""
    import pypdfium2 as pdfium

    with _LOCK:
        doc = pdfium.PdfDocument(pdf)
        try:
            if len(doc) != 1:
                raise ValueError(f"{pdf} has {len(doc)} pages; a page is one: split it with raster.pages")
            page = doc[0]
            bitmap = page.render(scale=scale(page.get_size()))
            try: return bitmap.to_pil()
            finally: bitmap.close()
        finally:
            doc.close()


def pages(doc: Path, folder: Path) -> list[Path]:
    """`doc`'s pages, in order, each a file: a PDF of several pages split into one-page PDFs in `folder`,
    its pages copied whole (text layer and fonts too); a one-page PDF or an image is one page, itself, so a
    page is sent as its file is. A file pdfium can't open is sent as it is too: its system says what it
    makes of it."""
    import pypdfium2 as pdfium

    if doc.suffix.lower() != ".pdf":
        return [doc]
    out = []
    with _LOCK:
        try:
            src = pdfium.PdfDocument(doc)
        except pdfium.PdfiumError:
            return [doc]
        try:
            if len(src) == 1:
                return [doc]
            for i in range(len(src)):
                one = pdfium.PdfDocument.new()
                try:
                    one.import_pages(src, [i])
                    one.save(path := folder / f"page-{i + 1:04d}.pdf")
                finally:
                    one.close()
                out.append(path)
        finally:
            src.close()
    return out
