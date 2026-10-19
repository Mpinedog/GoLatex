"""Proyecto abierto: rutas seguras, árbol de archivos y operaciones de archivo.

Toda ruta que llega de la API o del MCP es relativa a la raíz del proyecto y
se valida con `resolve()`: nunca se toca nada fuera de la carpeta abierta.
"""
import hashlib
import os
import re
import shutil
import time
from pathlib import Path

from send2trash import send2trash

from .config import ENGINES

# Artefactos de compilación: se ocultan del árbol y se ignoran en el watcher.
ARTIFACT_EXTS = {
    ".aux", ".log", ".fls", ".fdb_latexmk", ".out", ".toc", ".lof", ".lot",
    ".bbl", ".blg", ".bcf", ".nav", ".snm", ".vrb", ".xdv", ".dvi", ".idx",
    ".ilg", ".ind", ".glo", ".gls", ".glg", ".acn", ".acr", ".alg", ".loa",
}
ARTIFACT_SUFFIXES = (".synctex.gz", ".run.xml", ".synctex(busy)")
IGNORED_DIRS = {".git", ".svn", "node_modules", "__pycache__", ".venv", ".DS_Store"}

TEXT_EXTS = {
    ".tex", ".bib", ".bst", ".sty", ".cls", ".txt", ".md", ".csv", ".dat",
    ".sh", ".py", ".json", ".yaml", ".yml", ".gitignore",
}


class ProjectError(Exception):
    pass


class ConflictError(ProjectError):
    """El archivo cambió en disco desde que el cliente lo leyó."""

    def __init__(self, rel: str, current_hash: str | None):
        super().__init__(
            f"{rel} cambió en el disco desde que lo abriste (otro editor o el "
            "agente lo modificó). Recárgalo o elige mantener tu versión.")
        self.current_hash = current_hash


def is_artifact(path: Path) -> bool:
    name = path.name.lower()
    return path.suffix.lower() in ARTIFACT_EXTS or name.endswith(ARTIFACT_SUFFIXES)


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()[:16]


ENGINE_MAGIC = re.compile(r"^\s*%\s*!\s*TeX\s+(?:TS-)?program\s*=\s*(\w+)",
                          re.IGNORECASE | re.MULTILINE)
NEEDS_UNICODE_ENGINE = re.compile(r"\\usepackage(?:\[[^\]]*\])?\{[^}]*\b(?:fontspec|unicode-math|polyglossia)\b")


class Project:
    def __init__(self, root: str | Path, main: str | None = None,
                 engine: str | None = None):
        self.root = Path(root).expanduser().resolve()
        if not self.root.is_dir():
            raise ProjectError(f"No existe la carpeta: {self.root}")
        self.main = main or self._guess_main()
        # None = automático (comentario mágico / fontspec → xelatex; si no, pdflatex)
        self.engine_setting: str | None = engine if engine in ENGINES else None

    # ---------- rutas ----------

    def resolve(self, rel: str) -> Path:
        """Resuelve una ruta relativa dentro del proyecto; rechaza escapes."""
        rel = (rel or "").strip()
        if not rel:
            raise ProjectError("Ruta vacía")
        if Path(rel).is_absolute():
            raise ProjectError("Solo se aceptan rutas relativas al proyecto")
        p = (self.root / rel).resolve()
        if p != self.root and self.root not in p.parents:
            raise ProjectError(f"Ruta fuera del proyecto: {rel}")
        return p

    def relpath(self, p: Path) -> str:
        # siempre con '/', también en Windows: la UI, el log de LaTeX y el MCP
        # usan esa forma, así un mismo archivo tiene una sola clave
        return Path(p).resolve().relative_to(self.root).as_posix()

    # ---------- main / pdf ----------

    def _guess_main(self) -> str:
        if (self.root / "main.tex").exists():
            return "main.tex"
        candidates = sorted(self.root.glob("*.tex"))
        for c in candidates:
            try:
                if "\\documentclass" in c.read_text(encoding="utf-8", errors="replace"):
                    return c.name
            except OSError:
                continue
        return candidates[0].name if candidates else "main.tex"

    def set_main(self, rel: str) -> None:
        p = self.resolve(rel)
        if p.suffix != ".tex":
            raise ProjectError("El archivo principal debe ser .tex")
        self.main = self.relpath(p)

    # ---------- motor ----------

    @property
    def engine(self) -> str:
        """Motor efectivo: el fijado por el usuario o el detectado."""
        return self.engine_setting or self.detect_engine()

    def detect_engine(self) -> str:
        try:
            text = self.main_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "pdflatex"
        m = ENGINE_MAGIC.search(text[:4000])
        if m and m.group(1).lower() in ENGINES:
            return m.group(1).lower()
        body = re.sub(r"(?<!\\)%.*", "", text)
        if NEEDS_UNICODE_ENGINE.search(body):
            return "xelatex"
        return "pdflatex"

    def set_engine(self, engine: str | None) -> None:
        if engine in (None, "", "auto"):
            self.engine_setting = None
            return
        if engine not in ENGINES:
            raise ProjectError(f"Motor no soportado: {engine} (usa {', '.join(ENGINES)} o auto)")
        self.engine_setting = engine

    @property
    def main_path(self) -> Path:
        return self.root / self.main

    @property
    def pdf_path(self) -> Path:
        return self.main_path.with_suffix(".pdf")

    @property
    def log_path(self) -> Path:
        return self.main_path.with_suffix(".log")

    @property
    def synctex_path(self) -> Path:
        return Path(str(self.main_path.with_suffix("")) + ".synctex.gz")

    def inputs(self) -> list[str]:
        """Archivos incluidos desde el principal, recursivamente: \\input,
        \\include, \\subfile, \\import y \\subimport. Rutas con '/'."""
        found: list[str] = []
        seen: set[str] = set()
        rx = re.compile(
            r"\\(?P<cmd>input|include|subfile|import|subimport|inputfrom|subinputfrom)\*?"
            r"\s*\{(?P<a>[^}]*)\}(?:\s*\{(?P<b>[^}]*)\})?")

        def scan(rel: str):
            if rel in seen:
                return
            seen.add(rel)
            base = Path(rel).parent
            try:
                text = (self.root / rel).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return
            text = re.sub(r"(?<!\\)%.*", "", text)  # sin comentarios
            for m in rx.finditer(text):
                cmd, a, b = m.group("cmd"), m.group("a").strip(), (m.group("b") or "").strip()
                if cmd in ("import", "inputfrom"):          # ruta absoluta desde la raíz
                    name = (Path(a) / b).as_posix() if b else a
                elif cmd in ("subimport", "subinputfrom"):  # relativa al archivo actual
                    name = (base / a / b).as_posix() if b else a
                else:
                    name = a
                if not name or "#" in name:
                    continue
                if not name.endswith(".tex"):
                    name += ".tex"
                p = self.root / name
                if p.is_file():
                    name = self.relpath(p)
                    if name not in found:
                        found.append(name)
                    scan(name)

        scan(self.main)
        return found

    def pdf_is_current(self) -> bool:
        """True si el PDF existe y es más nuevo que todas las fuentes."""
        pdf = self.pdf_path
        if not pdf.exists():
            return False
        # +1s de tolerancia: latexmk puede tocar mtimes de fuentes al cerrar
        pdf_m = pdf.stat().st_mtime + 1.0
        for p in self.root.rglob("*"):
            if p.is_dir() or is_artifact(p) or p == pdf:
                continue
            if any(part in IGNORED_DIRS for part in p.parts):
                continue
            if p.suffix.lower() in {".tex", ".bib", ".bst", ".sty", ".cls"}:
                try:
                    if p.stat().st_mtime > pdf_m:
                        return False
                except OSError:
                    continue
        return True

    # ---------- árbol ----------

    def tree(self) -> list[dict]:
        def walk(d: Path) -> list[dict]:
            items = []
            try:
                entries = sorted(
                    d.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except OSError:
                return items
            for p in entries:
                if p.name.startswith(".") or p.name in IGNORED_DIRS:
                    continue
                if p.is_dir():
                    items.append({
                        "name": p.name, "path": self.relpath(p),
                        "type": "dir", "children": walk(p),
                    })
                else:
                    if is_artifact(p):
                        continue
                    items.append({
                        "name": p.name, "path": self.relpath(p), "type": "file",
                        "text": p.suffix.lower() in TEXT_EXTS,
                    })
            return items

        return walk(self.root)

    # ---------- archivos ----------

    def read_text(self, rel: str) -> tuple[str, str, float]:
        p = self.resolve(rel)
        if not p.is_file():
            raise ProjectError(f"No existe: {rel}")
        data = p.read_bytes()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1")
        return text, content_hash(data), p.stat().st_mtime

    def current_hash(self, rel: str) -> str | None:
        p = self.resolve(rel)
        try:
            return content_hash(p.read_bytes())
        except FileNotFoundError:
            return None

    def write_text(self, rel: str, content: str,
                   expected_hash: str | None = None) -> tuple[str, float]:
        """Escribe el archivo de forma atómica.

        Si `expected_hash` viene, el archivo debe seguir teniendo ese contenido
        (control optimista): si alguien más lo cambió entretanto, ConflictError
        en vez de pisar sus cambios en silencio."""
        p = self.resolve(rel)
        if expected_hash is not None:
            now = self.current_hash(rel)
            if now is not None and now != expected_hash:
                raise ConflictError(rel, now)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8")
        _atomic_write(p, data)
        return content_hash(data), p.stat().st_mtime

    def create_file(self, rel: str) -> None:
        p = self.resolve(rel)
        if p.exists():
            raise ProjectError(f"Ya existe: {rel}")
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch()

    def create_dir(self, rel: str) -> None:
        p = self.resolve(rel)
        if p.exists():
            raise ProjectError(f"Ya existe: {rel}")
        p.mkdir(parents=True)

    def rename(self, rel: str, new_rel: str) -> None:
        src = self.resolve(rel)
        dst = self.resolve(new_rel)
        if not src.exists():
            raise ProjectError(f"No existe: {rel}")
        if dst.exists():
            raise ProjectError(f"Ya existe: {new_rel}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        if self.relpath(src) == self.main:
            self.main = self.relpath(dst)

    def delete(self, rel: str) -> None:
        p = self.resolve(rel)
        if p == self.root:
            raise ProjectError("No se puede eliminar la raíz")
        if not p.exists():
            raise ProjectError(f"No existe: {rel}")
        send2trash(str(p))  # a la Papelera, recuperable

    # ---------- búsqueda ----------

    def search(self, pattern: str, case_sensitive: bool = False,
               max_results: int = 200) -> list[dict]:
        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            rx = re.compile(pattern, flags)
        except re.error as e:
            raise ProjectError(f"Regex inválida: {e}")
        results: list[dict] = []
        for p in sorted(self.root.rglob("*")):
            if len(results) >= max_results:
                break
            if (p.is_dir() or is_artifact(p)
                    or p.suffix.lower() not in TEXT_EXTS
                    or any(part in IGNORED_DIRS or part.startswith(".")
                           for part in p.relative_to(self.root).parts[:-1])):
                continue
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if rx.search(line):
                    results.append({
                        "file": self.relpath(p), "line": i,
                        "text": line.strip()[:300],
                    })
                    if len(results) >= max_results:
                        break
        return results


def _atomic_write(p: Path, data: bytes) -> None:
    """Escribe a un temporal oculto y lo renombra encima: un corte de luz o un
    error a mitad de camino nunca deja el .tex truncado. En Windows el rename
    falla si otro proceso tiene el archivo abierto (p. ej. LaTeX compilando);
    se reintenta un momento y, si sigue bloqueado, se escribe directo."""
    tmp = p.with_name(f".{p.name}.golatex-tmp")
    try:
        with open(tmp, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        for attempt in range(10):
            try:
                os.replace(tmp, p)
                return
            except PermissionError:
                time.sleep(0.05 * (attempt + 1))
        p.write_bytes(data)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass
