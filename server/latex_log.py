"""Parser del log de LaTeX: errores y warnings con archivo y línea.

Se compila con -file-line-error, así que los errores llegan como
`./archivo.tex:123: mensaje`. Para warnings (que no traen archivo) se
mantiene una pila de paréntesis del log para atribuirlos al archivo activo.
"""
import re
from pathlib import Path

# admite rutas relativas (./cap.tex) y absolutas de Windows (C:/.../cap.tex)
FILE_LINE_ERR = re.compile(
    r"^(?P<file>(?:[A-Za-z]:[\\/])?(?:\./)?[^:\s][^:]*?\.\w+):(?P<line>\d+):\s*(?P<msg>.*)$")
WIN_ABS = re.compile(r"^[A-Za-z]:[\\/]")
# biber: "[57] Biber.pm:131> WARN - I didn't find a database entry for 'x'"
BIBER_LINE = re.compile(r"^\[\d+\]\s+\S+>\s+(?P<level>WARN|ERROR)\s+-\s+(?P<msg>.*)$")
BANG_ERR = re.compile(r"^!\s*(?P<msg>.+)$")
LATEX_WARN = re.compile(r"^(?:LaTeX|Class \S+|Package \S+)\s+Warning:\s*(?P<msg>.*)$", re.IGNORECASE)
ON_LINE = re.compile(r"on input line (?P<line>\d+)")
OUTPUT_PAGES = re.compile(r"Output written on .*?\((?P<pages>\d+) pages?")


def _unwrap(text: str, width: int = 79) -> list[str]:
    """TeX corta el log a 79 columnas; re-une las líneas partidas."""
    out: list[str] = []
    buf = ""
    for raw in text.splitlines():
        buf += raw
        if len(raw) != width:
            out.append(buf)
            buf = ""
    if buf:
        out.append(buf)
    return out


def _clean_file(name: str) -> str:
    name = name.strip().replace("\\", "/")
    if name.startswith("./"):
        name = name[2:]
    return name


def _relative(name: str, root: Path | None) -> str:
    """Ruta relativa a la raíz del proyecto (con '/') si cae dentro de ella."""
    name = _clean_file(name)
    if root and (name.startswith("/") or WIN_ABS.match(name)):
        try:
            return Path(name).resolve().relative_to(root).as_posix()
        except (ValueError, OSError):
            return name
    return name


class _FileStack:
    """Sigue los `(archivo ... )` del log para saber el archivo activo."""

    TOKEN = re.compile(r"\(((?:\./|\.\./|/)?[^\s()]+\.(?:tex|sty|cls|bib|bst|def|cfg|clo|fd|ldf))|\(|\)")

    def __init__(self, root: Path | None):
        self.root = root
        self.stack: list[str | None] = []

    def feed(self, line: str) -> None:
        for m in self.TOKEN.finditer(line):
            tok = m.group(0)
            if tok == ")":
                if self.stack:
                    self.stack.pop()
            elif m.group(1):
                self.stack.append(m.group(1))
            else:  # "(" sin archivo
                self.stack.append(None)

    def current(self) -> str | None:
        for item in reversed(self.stack):
            if item:
                return self._relative(item)
        return None

    def _relative(self, name: str) -> str:
        return _relative(name, self.root)


def parse_log(log_text: str, root: Path | None = None) -> dict:
    """Devuelve {errors: [...], warnings: [...], pages: int|None}."""
    lines = _unwrap(log_text)
    stack = _FileStack(root)
    errors: list[dict] = []
    warnings: list[dict] = []
    pages = None

    i = 0
    while i < len(lines):
        line = lines[i]

        m = FILE_LINE_ERR.match(line)
        if m and not line.startswith("l."):
            msg = m.group("msg").strip()
            # las líneas de contexto que siguen (hasta l.N o vacío) dan detalle
            detail = []
            j = i + 1
            while j < len(lines) and j <= i + 4:
                nxt = lines[j].strip()
                if not nxt or FILE_LINE_ERR.match(lines[j]) or nxt.startswith("!"):
                    break
                detail.append(nxt)
                if nxt.startswith("l."):
                    break
                j += 1
            if detail:
                msg = msg + " — " + " ".join(detail)[:200]
            errors.append({
                "file": _relative(m.group("file"), root),
                "line": int(m.group("line")),
                "message": msg.strip(),
                "type": "error",
            })
            stack.feed(line)
            i += 1
            continue

        m = BANG_ERR.match(line)
        if m:
            msg = m.group("msg").strip()
            if msg and not msg.startswith("=="):
                line_no = None
                j = i + 1
                while j < len(lines) and j <= i + 6:
                    lm = re.match(r"^l\.(\d+)", lines[j].strip())
                    if lm:
                        line_no = int(lm.group(1))
                        break
                    j += 1
                errors.append({
                    "file": stack.current(),
                    "line": line_no,
                    "message": msg,
                    "type": "error",
                })
            i += 1
            continue

        m = LATEX_WARN.match(line.strip())
        if m:
            msg = m.group("msg").strip()
            lm = ON_LINE.search(msg)
            warnings.append({
                "file": stack.current(),
                "line": int(lm.group("line")) if lm else None,
                "message": msg,
                "type": "warning",
            })
            stack.feed(line)
            i += 1
            continue

        m = OUTPUT_PAGES.search(line)
        if m:
            pages = int(m.group("pages"))

        stack.feed(line)
        i += 1

    # dedup conservando orden
    def dedup(items):
        seen, out = set(), []
        for it in items:
            key = (it["file"], it["line"], it["message"])
            if key not in seen:
                seen.add(key)
                out.append(it)
        return out

    return {"errors": dedup(errors), "warnings": dedup(warnings), "pages": pages}


def parse_blg(blg_text: str) -> list[dict]:
    """Errores/warnings de BibTeX o de biber (main.blg)."""
    items: list[dict] = []
    for line in blg_text.splitlines():
        m = BIBER_LINE.match(line.strip())
        if m:
            items.append({"file": None, "line": None,
                          "message": f"biber: {m.group('msg').strip()}",
                          "type": "error" if m.group("level") == "ERROR" else "warning"})
            continue
        if line.startswith("Warning--"):
            items.append({"file": None, "line": None,
                          "message": f"BibTeX: {line[len('Warning--'):].strip()}",
                          "type": "warning"})
            continue
        m = re.match(r"^(.+)---line (\d+) of file (.+)$", line.strip())
        if m:
            items.append({"file": _clean_file(m.group(3)),
                          "line": int(m.group(2)),
                          "message": f"BibTeX: {m.group(1).strip()}",
                          "type": "error"})
    return items
