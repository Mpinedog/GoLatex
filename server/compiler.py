"""Compilación con latexmk: cola única compartida entre la UI y el MCP."""
import asyncio
import subprocess
import time

from .config import ENGINES, tex_cmd, tex_env, tex_install_hint
from .latex_log import parse_blg, parse_log
from .project import Project

LATEXMK_ARGS = ["-interaction=nonstopmode", "-file-line-error", "-synctex=1"]
TIMEOUT = 300  # segundos


def _fail(source: str, message: str) -> dict:
    return {"ok": False, "source": source, "exit_code": -1, "pages": None,
            "errors": [{"file": None, "line": None, "type": "error",
                        "message": message}],
            "warnings": []}


class Compiler:
    """Un solo latexmk a la vez; si humano y agente compilan juntos, se encolan."""

    def __init__(self, project: Project, bus):
        self.project = project
        self.bus = bus
        self._lock = asyncio.Lock()
        self.compiling = False
        self.last_result: dict | None = None

    async def compile(self, source: str = "ui") -> dict:
        async with self._lock:
            self.compiling = True
            self.bus.broadcast({"type": "compile_started", "source": source})
            t0 = time.monotonic()
            try:
                result = await self._run(source)
            finally:
                self.compiling = False
            result["seconds"] = round(time.monotonic() - t0, 2)
            self.last_result = result
            self.bus.broadcast({"type": "compile_finished", **result})
            return result

    def _latexmk(self) -> list[str] | None:
        exe = tex_cmd("latexmk")
        if not exe:
            return None
        flag = ENGINES.get(self.project.engine, "-pdf")
        return [exe, flag, *LATEXMK_ARGS, self.project.main]

    async def _run(self, source: str) -> dict:
        proj = self.project
        cmd = self._latexmk()
        if not cmd:
            return _fail(source, f"latexmk no encontrado: {tex_install_hint()}")

        # subprocess.run en un hilo (y no asyncio.create_subprocess_exec):
        # funciona igual con cualquier event loop, incluido el SelectorEventLoop
        # que uvicorn usa en Windows con --reload, que no soporta subprocesos.
        def run():
            return subprocess.run(
                cmd, cwd=str(proj.root), env=tex_env(),
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL, timeout=TIMEOUT,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )

        try:
            done = await asyncio.to_thread(run)
        except subprocess.TimeoutExpired:
            return _fail(source, f"latexmk superó el tiempo límite de {TIMEOUT}s")
        except FileNotFoundError:
            return _fail(source, f"latexmk no encontrado: {tex_install_hint()}")
        exit_code = done.returncode
        stdout = done.stdout.decode("utf-8", errors="replace")

        parsed = {"errors": [], "warnings": [], "pages": None}
        if proj.log_path.exists():
            parsed = parse_log(proj.log_path.read_text(encoding="utf-8", errors="replace"),
                               proj.root)
        else:
            tail = stdout[-2000:]
            if "perl" in stdout.lower() and ("not find" in stdout.lower()
                                             or "no se" in stdout.lower()):
                tail = ("latexmk necesita Perl. En Windows: winget install "
                        "StrawberryPerl.StrawberryPerl y reinicia GoLatex.\n\n" + tail)
            parsed["errors"].append({"file": None, "line": None, "type": "error",
                                     "message": f"No se generó el log. Salida: {tail}"})

        blg = proj.main_path.with_suffix(".blg")
        if blg.exists():
            for item in parse_blg(blg.read_text(encoding="utf-8", errors="replace")):
                (parsed["errors"] if item["type"] == "error" else parsed["warnings"]).append(item)

        ok = exit_code == 0 and not parsed["errors"]
        pages = parsed.get("pages")
        if proj.pdf_path.exists():
            try:
                from . import pdf_utils
                pages = pdf_utils.page_count(proj.pdf_path)
            except Exception:
                pass

        return {
            "ok": ok,
            "source": source,
            "engine": proj.engine,
            "exit_code": exit_code,
            "pages": pages,
            "errors": parsed["errors"][:50],
            "warnings": parsed["warnings"][:100],
        }

    def get_log(self) -> str:
        if self.project.log_path.exists():
            return self.project.log_path.read_text(encoding="utf-8", errors="replace")
        return "(aún no hay log; compila primero)"
