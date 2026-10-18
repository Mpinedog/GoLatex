"""Utilidades de PDF con PyMuPDF: conteo de páginas y render a PNG."""
from pathlib import Path

try:
    import pymupdf as fitz  # PyMuPDF >= 1.24
except ImportError:  # versiones antiguas
    import fitz


def page_count(pdf: Path) -> int:
    with fitz.open(pdf) as doc:
        return doc.page_count


def render_page_png(pdf: Path, page: int, dpi: int = 144) -> bytes:
    """Renderiza la página `page` (1-indexada) como PNG."""
    with fitz.open(pdf) as doc:
        if not 1 <= page <= doc.page_count:
            raise ValueError(f"Página {page} fuera de rango (1..{doc.page_count})")
        dpi = max(36, min(dpi, 300))
        pix = doc[page - 1].get_pixmap(dpi=dpi)
        return pix.tobytes("png")
