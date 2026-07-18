"""Compilación con latexmk: cola única compartida entre la UI y el MCP."""
import asyncio
import time

from .config import tex_env
from .latex_log import parse_blg, parse_log
from .project import Project

LATEXMK_ARGS = ["-pdf", "-interaction=nonstopmode", "-file-line-error", "-synctex=1"]
TIMEOUT = 300  # segundos


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

    async def _run(self, source: str) -> dict:
        proj = self.project
        cmd = ["latexmk", *LATEXMK_ARGS, proj.main]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=str(proj.root),
                env=tex_env(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            try:
                stdout, _ = await asyncio.wait_for(proc.communicate(), TIMEOUT)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return {"ok": False, "source": source, "exit_code": -1, "pages": None,
                        "errors": [{"file": None, "line": None, "type": "error",
                                    "message": f"latexmk superó el tiempo límite de {TIMEOUT}s"}],
                        "warnings": []}
            exit_code = proc.returncode
        except FileNotFoundError:
            return {"ok": False, "source": source, "exit_code": -1, "pages": None,
                    "errors": [{"file": None, "line": None, "type": "error",
                                "message": "latexmk no encontrado; revisa /Library/TeX/texbin"}],
                    "warnings": []}

        parsed = {"errors": [], "warnings": [], "pages": None}
        if proj.log_path.exists():
            parsed = parse_log(proj.log_path.read_text(errors="replace"), proj.root)
        else:
            tail = stdout.decode(errors="replace")[-2000:]
            parsed["errors"].append({"file": None, "line": None, "type": "error",
                                     "message": f"No se generó el log. Salida: {tail}"})

        blg = proj.main_path.with_suffix(".blg")
        if blg.exists():
            for item in parse_blg(blg.read_text(errors="replace")):
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
            "exit_code": exit_code,
            "pages": pages,
            "errors": parsed["errors"][:50],
            "warnings": parsed["warnings"][:100],
        }

    def get_log(self) -> str:
        if self.project.log_path.exists():
            return self.project.log_path.read_text(errors="replace")
        return "(aún no hay log; compila primero)"
