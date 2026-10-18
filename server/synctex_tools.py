"""SyncTeX: mapeo código ↔ PDF usando el CLI `synctex` de TeX Live."""
import re
import subprocess
from pathlib import Path

from .config import tex_cmd, tex_env, tex_install_hint
from .project import Project, ProjectError


def _run(args: list[str], cwd: Path) -> str:
    exe = tex_cmd("synctex")
    if not exe:
        raise ProjectError(f"synctex no encontrado: {tex_install_hint()}")
    try:
        out = subprocess.run(
            [exe, *args[1:]], cwd=str(cwd), env=tex_env(),
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return out.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        raise ProjectError(f"synctex falló: {e}")


def forward(project: Project, file_rel: str, line: int, col: int = 0) -> dict:
    """Código → PDF. Devuelve {page, x, y, h, v, width, height}."""
    src = project.resolve(file_rel)
    out = _run(
        ["synctex", "view", "-i", f"{line}:{max(col, 1)}:{src}",
         "-o", str(project.pdf_path)],
        project.root,
    )
    rec: dict = {}
    for ln in out.splitlines():
        m = re.match(r"^(Page|x|y|h|v|W|H):(.*)$", ln.strip())
        if m:
            key, val = m.group(1), m.group(2).strip()
            if key == "Page" and "page" not in rec:
                rec["page"] = int(val)
            elif key in ("x", "y", "h", "v", "W", "H") and key.lower() not in rec:
                name = {"W": "width", "H": "height"}.get(key, key)
                rec.setdefault(name, float(val))
        if len(rec) >= 7:
            break
    if "page" not in rec:
        raise ProjectError("SyncTeX no encontró esa línea (¿compilaste con synctex?)")
    return rec


def inverse(project: Project, page: int, x: float, y: float) -> dict:
    """PDF → código. Devuelve {file, line, column}."""
    out = _run(
        ["synctex", "edit", "-o", f"{page}:{x}:{y}:{project.pdf_path}"],
        project.root,
    )
    rec: dict = {}
    for ln in out.splitlines():
        m = re.match(r"^(Input|Line|Column):(.*)$", ln.strip())
        if m:
            key, val = m.group(1).lower(), m.group(2).strip()
            if key not in rec:
                rec[key] = val
        if len(rec) >= 3:
            break
    if "input" not in rec or "line" not in rec:
        raise ProjectError("SyncTeX no pudo mapear ese punto del PDF")
    src = Path(rec["input"])
    if not src.is_absolute():
        src = project.root / src
    try:
        file_rel = src.resolve().relative_to(project.root).as_posix()
    except (ValueError, OSError):
        file_rel = rec["input"].replace("\\", "/")
    return {"file": file_rel, "line": int(rec["line"]),
            "column": int(rec.get("column", 0) or 0)}
