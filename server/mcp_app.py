"""Cara agéntica de GoLatex: servidor MCP (Streamable HTTP).

Comparte STATE con la app web: mismo proyecto, misma cola de compilación,
y cada escritura dispara los eventos en vivo que la UI muestra al tiro.
"""
from typing import Optional

from mcp.server.fastmcp import FastMCP, Image

from . import ai_detect
from . import bib as bib_tools
from . import pdf_utils
from .project import ProjectError
from .state import STATE

mcp = FastMCP(
    "golatex",
    instructions=(
        "Workspace LaTeX local GoLatex. Trabaja siempre sobre el proyecto "
        "abierto en la app; usa project_info para orientarte, compile para "
        "compilar (errores ya parseados) y render_page para VER una página "
        "del PDF."
    ),
    stateless_http=True,
    json_response=True,
)


@mcp.tool()
def project_info() -> dict:
    """Información del proyecto abierto: raíz, archivo principal, capítulos
    incluidos con \\input, y si el PDF está al día respecto de las fuentes."""
    p = STATE.require_project()
    pdf_exists = p.pdf_path.exists()
    return {
        "root": str(p.root),
        "main": p.main,
        "inputs": p.inputs(),
        "pdf": p.pdf_path.name if pdf_exists else None,
        "pdf_exists": pdf_exists,
        "pdf_up_to_date": p.pdf_is_current(),
        "pages": pdf_utils.page_count(p.pdf_path) if pdf_exists else None,
        "last_compile_ok": (STATE.compiler.last_result or {}).get("ok")
        if STATE.compiler else None,
    }


@mcp.tool()
def list_files() -> list:
    """Árbol de archivos del proyecto (sin artefactos de compilación)."""
    return STATE.require_project().tree()


@mcp.tool()
def read_file(path: str) -> str:
    """Lee un archivo de texto del proyecto. `path` es relativo a la raíz
    (p. ej. 'capitulo_2.tex')."""
    content, _, _ = STATE.require_project().read_text(path)
    return content


@mcp.tool()
def write_file(path: str, content: str) -> dict:
    """Escribe (o crea) un archivo de texto completo. Para cambios puntuales
    prefiere edit_file. La UI del humano se refresca en vivo."""
    project = STATE.require_project()
    h, mtime = project.write_text(path, content)
    return {"ok": True, "path": path, "bytes": len(content.encode("utf-8"))}


@mcp.tool()
def edit_file(path: str, old_string: str, new_string: str,
              replace_all: bool = False) -> dict:
    """Reemplazo puntual dentro de un archivo: `old_string` debe existir tal
    cual; si aparece más de una vez y replace_all es False, es un error
    (agrega contexto para hacerlo único)."""
    project = STATE.require_project()
    content, _, _ = project.read_text(path)
    count = content.count(old_string)
    if count == 0:
        raise ProjectError(f"No se encontró el texto a reemplazar en {path}")
    if count > 1 and not replace_all:
        raise ProjectError(
            f"El texto aparece {count} veces en {path}; agrega contexto para "
            "hacerlo único o usa replace_all=true")
    if replace_all:
        new_content = content.replace(old_string, new_string)
    else:
        new_content = content.replace(old_string, new_string, 1)
    project.write_text(path, new_content)
    return {"ok": True, "path": path, "replacements": count if replace_all else 1}


@mcp.tool()
async def compile() -> dict:
    """Compila el proyecto con latexmk (cola compartida con la app: si el
    humano está compilando, espera su turno). Devuelve estado, errores y
    warnings parseados (archivo, línea, mensaje) y número de páginas."""
    STATE.require_project()
    return await STATE.compiler.compile(source="mcp")


@mcp.tool()
def get_log() -> str:
    """Log crudo completo de la última compilación (bajo demanda)."""
    STATE.require_project()
    log = STATE.compiler.get_log()
    limit = 200_000
    if len(log) > limit:
        return log[:limit // 2] + "\n\n[... log truncado ...]\n\n" + log[-limit // 2:]
    return log


@mcp.tool()
def render_page(page: int, dpi: int = 144) -> Image:
    """Devuelve la página `page` (1-indexada) del PDF compilado como imagen
    PNG, para VER el resultado real (figuras, layout, tablas)."""
    p = STATE.require_project()
    if not p.pdf_path.exists():
        raise ProjectError("No hay PDF; compila primero")
    png = pdf_utils.render_page_png(p.pdf_path, page, dpi)
    return Image(data=png, format="png")


@mcp.tool()
def search(pattern: str, case_sensitive: bool = False,
           max_results: int = 100) -> list:
    """Busca una expresión regular en los archivos de texto del proyecto.
    Devuelve [{file, line, text}]."""
    return STATE.require_project().search(pattern, case_sensitive, max_results)


@mcp.tool()
def bib_list(bib_file: Optional[str] = None) -> dict:
    """Lista las entradas del .bib del proyecto (clave, tipo, título, autor,
    año). Sin `bib_file` usa references.bib o el primero que encuentre."""
    return bib_tools.list_entries(STATE.require_project(), bib_file)


@mcp.tool()
def ai_check(path: Optional[str] = None, text: Optional[str] = None,
             lang: str = "es") -> dict:
    """Estima qué tan "IA" suena un texto (detector local texthumanize, sin
    red). Pasa `path` (un .tex del proyecto: se limpia el LaTeX y se analiza
    la prosa) o `text` directo; `lang` por defecto 'es'. Devuelve score 0-1
    (0=humano, 1=IA), verdict, confianza, señales dominantes y los párrafos
    más sospechosos. Es ORIENTATIVO: ningún detector de IA es concluyente."""
    return ai_detect.analyze(STATE.project, path, text, lang)


@mcp.tool()
def bib_add(entry: str, bib_file: Optional[str] = None) -> dict:
    """Agrega una entrada BibTeX completa (texto '@tipo{clave, ...}') al .bib
    del proyecto, validando llaves y clave duplicada."""
    return bib_tools.add_entry(STATE.require_project(), entry, bib_file)
