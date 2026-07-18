"""Configuración persistente de GoLatex (~/.golatex/state.json) y entorno TeX."""
import json
import os
from pathlib import Path

TEXBIN = "/Library/TeX/texbin"
CONFIG_DIR = Path.home() / ".golatex"
CONFIG_FILE = CONFIG_DIR / "state.json"

PORT = int(os.environ.get("GOLATEX_PORT", "8123"))


def tex_env() -> dict:
    """Entorno para subprocesos de TeX. Los procesos GUI de macOS no heredan
    el PATH del shell, así que /Library/TeX/texbin se agrega siempre."""
    env = os.environ.copy()
    path = env.get("PATH", "/usr/bin:/bin:/usr/sbin:/sbin")
    if TEXBIN not in path.split(":"):
        env["PATH"] = f"{TEXBIN}:{path}"
    return env


def load_config() -> dict:
    try:
        with open(CONFIG_FILE) as f:
            cfg = json.load(f)
    except (OSError, json.JSONDecodeError):
        cfg = {}
    cfg.setdefault("recents", [])  # [{path, main, opened_at}]
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    tmp.replace(CONFIG_FILE)
