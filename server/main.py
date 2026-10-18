"""GoLatex: app FastAPI (REST + WebSocket + estáticos) con el MCP montado en /mcp."""
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import bib as bib_tools
from . import pdf_utils, synctex_tools
from .config import ENGINES
from .mcp_app import mcp
from .project import ProjectError
from .state import STATE

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("golatex")

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@asynccontextmanager
async def lifespan(app: FastAPI):
    STATE.bus.attach_loop()
    auto = os.environ.get("GOLATEX_OPEN")
    if not auto:
        for r in STATE.config["recents"]:
            if Path(r["path"]).is_dir():
                auto = r["path"]
                break
    if auto:
        try:
            p = STATE.open_project(auto)
            log.info("Proyecto abierto: %s (main=%s)", p.root, p.main)
        except ProjectError as e:
            log.warning("No se pudo abrir %s: %s", auto, e)
    async with mcp.session_manager.run():
        yield
    STATE.close_project()


app = FastAPI(title="GoLatex", lifespan=lifespan)


@app.exception_handler(ProjectError)
async def project_error_handler(request, exc: ProjectError):
    return JSONResponse(status_code=400, content={"detail": str(exc)})


# ---------- modelos ----------

class OpenBody(BaseModel):
    path: str


class FileBody(BaseModel):
    path: str
    content: str


class FsCreateBody(BaseModel):
    path: str
    type: str = "file"  # "file" | "dir"


class RenameBody(BaseModel):
    path: str
    new_path: str


class PathBody(BaseModel):
    path: str


class EngineBody(BaseModel):
    engine: str | None = None  # pdflatex | xelatex | lualatex | None/"auto"


# ---------- estado / proyecto ----------

def _project_dict():
    p = STATE.project
    if not p:
        return None
    return {"root": str(p.root), "name": p.root.name, "main": p.main,
            "engine": p.engine, "engine_setting": p.engine_setting,
            "engines": list(ENGINES), "pdf_exists": p.pdf_path.exists()}


@app.get("/api/state")
def get_state():
    recents = [r for r in STATE.config["recents"] if Path(r["path"]).is_dir()]
    last = STATE.compiler.last_result if STATE.compiler else None
    return {"project": _project_dict(), "recents": recents,
            "compiling": STATE.compiler.compiling if STATE.compiler else False,
            "last_compile": last}


@app.post("/api/project/open")
def open_project(body: OpenBody):
    p = STATE.open_project(body.path)
    return {"project": _project_dict(), "tree": p.tree()}


@app.post("/api/main")
def set_main(body: PathBody):
    STATE.set_main(body.path)
    return {"main": STATE.project.main}


@app.post("/api/engine")
def set_engine(body: EngineBody):
    STATE.set_engine(body.engine)
    p = STATE.project
    return {"engine": p.engine, "engine_setting": p.engine_setting}


@app.get("/api/browse")
def browse(path: str = ""):
    """Selector de carpetas: lista subdirectorios de una ruta del usuario."""
    base = Path(path).expanduser() if path else Path.home()
    try:
        base = base.resolve()
        if not base.is_dir():
            raise HTTPException(404, f"No es una carpeta: {base}")
        dirs = sorted(
            [d.name for d in base.iterdir()
             if d.is_dir() and not d.name.startswith(".")],
            key=str.lower)
        has_tex = any(base.glob("*.tex"))
    except PermissionError:
        raise HTTPException(403, f"Sin permiso para leer {base}")
    return {"path": str(base), "sep": os.sep,
            "parent": str(base.parent) if base != base.parent else None,
            "dirs": dirs, "has_tex": has_tex}


# ---------- árbol y archivos ----------

@app.get("/api/tree")
def get_tree():
    return STATE.require_project().tree()


@app.get("/api/file")
def read_file(path: str):
    content, h, mtime = STATE.require_project().read_text(path)
    return {"path": path, "content": content, "hash": h, "mtime": mtime}


@app.put("/api/file")
def write_file(body: FileBody):
    h, mtime = STATE.require_project().write_text(body.path, body.content)
    return {"path": body.path, "hash": h, "mtime": mtime}


@app.post("/api/fs/create")
def fs_create(body: FsCreateBody):
    p = STATE.require_project()
    if body.type == "dir":
        p.create_dir(body.path)
    else:
        p.create_file(body.path)
    return {"ok": True}


@app.post("/api/fs/rename")
def fs_rename(body: RenameBody):
    STATE.require_project().rename(body.path, body.new_path)
    return {"ok": True, "main": STATE.project.main}


@app.post("/api/fs/delete")
def fs_delete(body: PathBody):
    STATE.require_project().delete(body.path)
    return {"ok": True}


@app.get("/api/raw")
def raw_file(path: str):
    p = STATE.require_project().resolve(path)
    if not p.is_file():
        raise HTTPException(404, f"No existe: {path}")
    return FileResponse(p, headers={"Cache-Control": "no-store"})


# ---------- compilación / pdf ----------

@app.post("/api/compile")
async def compile_project():
    STATE.require_project()
    return await STATE.compiler.compile(source="ui")


@app.get("/api/log", response_class=PlainTextResponse)
def get_log():
    STATE.require_project()
    return STATE.compiler.get_log()


@app.get("/api/pdf")
def get_pdf():
    p = STATE.require_project()
    if not p.pdf_path.exists():
        raise HTTPException(404, "Aún no hay PDF; compila primero")
    return FileResponse(p.pdf_path, media_type="application/pdf",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/page.png")
def page_png(page: int, dpi: int = 144):
    p = STATE.require_project()
    if not p.pdf_path.exists():
        raise HTTPException(404, "Aún no hay PDF")
    try:
        png = pdf_utils.render_page_png(p.pdf_path, page, dpi)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "no-store"})


# ---------- synctex ----------

@app.get("/api/synctex/forward")
def synctex_forward(file: str, line: int, col: int = 1):
    return synctex_tools.forward(STATE.require_project(), file, line, col)


@app.get("/api/synctex/inverse")
def synctex_inverse(page: int, x: float, y: float):
    return synctex_tools.inverse(STATE.require_project(), page, x, y)


# ---------- bib ----------

@app.get("/api/bib")
def bib_list(bib_file: str | None = None):
    return bib_tools.list_entries(STATE.require_project(), bib_file)


# ---------- websocket ----------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await STATE.bus.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keepalive del cliente; se ignora
    except WebSocketDisconnect:
        pass
    finally:
        STATE.bus.disconnect(ws)


# ---------- MCP y estáticos ----------

class _MCPPathFix:
    """El mount de Starlette atiende /mcp/; los clientes MCP postean a /mcp."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/mcp":
            scope["path"] = "/mcp/"
            scope["raw_path"] = b"/mcp/"
        await self.app(scope, receive, send)


app.add_middleware(_MCPPathFix)
mcp.settings.streamable_http_path = "/"
app.mount("/mcp", mcp.streamable_http_app())
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
