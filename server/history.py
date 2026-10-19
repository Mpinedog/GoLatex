"""Historial con git: puntos de control del proyecto LaTeX.

Un agente puede reescribir un capítulo entero con write_file; sin historial
no hay cómo volver atrás. `checkpoint` hace `git add` + `git commit` (y
opcionalmente `git push`) solo sobre la carpeta del proyecto.
"""
import shutil
import subprocess

from .project import Project, ProjectError

LATEX_GITIGNORE = """\
# artefactos de LaTeX (los genera latexmk; no se versionan)
*.aux
*.log
*.out
*.toc
*.lof
*.lot
*.fls
*.fdb_latexmk
*.synctex.gz
*.synctex(busy)
*.bbl
*.blg
*.bcf
*.run.xml
*.xdv
*.dvi
.*.golatex-tmp
"""


def _git(project: Project, *args: str, check: bool = True) -> str:
    exe = shutil.which("git")
    if not exe:
        raise ProjectError("git no está instalado (https://git-scm.com)")
    done = subprocess.run(
        [exe, *args], cwd=str(project.root), capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=120, stdin=subprocess.DEVNULL,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if check and done.returncode != 0:
        raise ProjectError(f"git {args[0]} falló: {(done.stderr or done.stdout).strip()}")
    return done.stdout.strip()


def _is_repo(project: Project) -> bool:
    try:
        return _git(project, "rev-parse", "--is-inside-work-tree") == "true"
    except ProjectError:
        return False


def checkpoint(project: Project, message: str, push: bool = False,
               init: bool = False) -> dict:
    message = (message or "").strip()
    if not message:
        raise ProjectError("Indica un mensaje que diga qué cambió")
    if not _is_repo(project):
        if not init:
            raise ProjectError(
                "La carpeta del proyecto no es un repositorio git; usa init=true "
                "para crearlo (agrega un .gitignore de LaTeX)")
        _git(project, "init")
        gi = project.root / ".gitignore"
        if not gi.exists():
            gi.write_text(LATEX_GITIGNORE, encoding="utf-8")

    _git(project, "add", "-A", "--", ".")
    staged = _git(project, "diff", "--cached", "--name-status", "--", ".")
    if not staged:
        return {"committed": False, "detail": "Sin cambios desde el último punto de control"}
    _git(project, "commit", "-q", "-m", message, "--", ".")
    result = {
        "committed": True,
        "commit": _git(project, "rev-parse", "--short", "HEAD"),
        "files": staged.splitlines(),
    }
    if push:
        try:
            _git(project, "push", "-q")
            result["pushed"] = True
        except ProjectError as e:
            result["pushed"] = False
            result["push_error"] = str(e)
    return result


def log(project: Project, n: int = 10) -> list[dict]:
    if not _is_repo(project):
        return []
    n = max(1, min(int(n), 100))
    out = _git(project, "log", f"-{n}", "--date=iso-strict",
               "--pretty=format:%h%x1f%ad%x1f%s", "--", ".")
    rows = []
    for line in filter(None, out.splitlines()):
        h, date, subject = line.split("\x1f", 2)
        rows.append({"commit": h, "date": date, "message": subject})
    return rows
