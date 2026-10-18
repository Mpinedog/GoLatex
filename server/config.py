"""Configuración persistente de GoLatex (~/.golatex/state.json) y entorno TeX.

Multiplataforma: busca los binarios de TeX (latexmk, synctex, perl) en las
rutas típicas de macOS (MacTeX), Windows (MiKTeX / TeX Live / Strawberry Perl)
y Linux (TeX Live), además del PATH. `GOLATEX_TEXBIN` fuerza una carpeta.
"""
import json
import os
import shutil
import sys
from glob import glob
from pathlib import Path

IS_WINDOWS = os.name == "nt"
IS_MAC = sys.platform == "darwin"

CONFIG_DIR = Path.home() / ".golatex"
CONFIG_FILE = CONFIG_DIR / "state.json"

PORT = int(os.environ.get("GOLATEX_PORT", "8123"))

# Motores soportados → flag de latexmk
ENGINES = {
    "pdflatex": "-pdf",
    "xelatex": "-xelatex",
    "lualatex": "-lualatex",
}


def _texbin_candidates() -> list[str]:
    """Carpetas donde suele vivir TeX (y Perl, que latexmk necesita)."""
    cands: list[str] = []
    forced = os.environ.get("GOLATEX_TEXBIN")
    if forced:
        cands.append(forced)
    if IS_MAC:
        cands.append("/Library/TeX/texbin")
    elif IS_WINDOWS:
        local = os.environ.get("LOCALAPPDATA", "")
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        cands += [
            os.path.join(local, "Programs", "MiKTeX", "miktex", "bin", "x64"),
            os.path.join(pf, "MiKTeX", "miktex", "bin", "x64"),
        ]
        cands += sorted(glob(r"C:\texlive\*\bin\windows"), reverse=True)
        cands += sorted(glob(r"C:\texlive\*\bin\win64"), reverse=True)
        cands += [r"C:\Strawberry\perl\bin", r"C:\Strawberry\c\bin"]
    else:
        cands += sorted(glob("/usr/local/texlive/*/bin/*"), reverse=True)
    return [c for c in cands if c and os.path.isdir(c)]


def tex_env() -> dict:
    """Entorno para subprocesos de TeX. Los procesos GUI (y los servicios en
    Windows) no siempre heredan el PATH del shell, así que se anteponen las
    carpetas de TeX conocidas. Usa os.pathsep (';' en Windows, ':' en Unix)."""
    env = os.environ.copy()
    parts = [p for p in env.get("PATH", "").split(os.pathsep) if p]
    norm = {os.path.normcase(os.path.normpath(p)) for p in parts}
    extra = [c for c in _texbin_candidates()
             if os.path.normcase(os.path.normpath(c)) not in norm]
    env["PATH"] = os.pathsep.join(extra + parts)
    return env


def tex_cmd(name: str) -> str | None:
    """Ruta completa a un ejecutable de TeX, buscando en el PATH ampliado.

    En Windows, CreateProcess busca en el PATH del proceso padre (no en el
    `env` que se le pasa al hijo), así que se resuelve aquí la ruta absoluta."""
    return shutil.which(name, path=tex_env()["PATH"])


def tex_install_hint() -> str:
    if IS_WINDOWS:
        return ("instala MiKTeX (winget install MiKTeX.MiKTeX) y Strawberry Perl "
                "(winget install StrawberryPerl.StrawberryPerl), o define "
                "GOLATEX_TEXBIN con la carpeta de los binarios")
    if IS_MAC:
        return "instala MacTeX o revisa /Library/TeX/texbin"
    return "instala TeX Live (latexmk, synctex) o define GOLATEX_TEXBIN"


def load_config() -> dict:
    try:
        with open(CONFIG_FILE, encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        cfg = {}
    cfg.setdefault("recents", [])  # [{path, main, engine, opened_at}]
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    tmp.replace(CONFIG_FILE)
