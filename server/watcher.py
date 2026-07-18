"""Observa el sistema de archivos del proyecto y difunde eventos a la UI.

Así, cuando un agente MCP (u otro editor) escribe un archivo, la app lo ve
al instante; y si aparece un PDF nuevo, el visor se refresca solo.
"""
import logging
from pathlib import Path

from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from .project import IGNORED_DIRS, Project, content_hash, is_artifact

log = logging.getLogger("golatex.watcher")


class _Handler(FileSystemEventHandler):
    def __init__(self, project: Project, bus, compiler):
        self.project = project
        self.bus = bus
        self.compiler = compiler

    def _rel(self, raw_path: str) -> str | None:
        p = Path(raw_path)
        try:
            rel = p.resolve().relative_to(self.project.root)
        except (ValueError, OSError):
            return None
        if any(part in IGNORED_DIRS or part.startswith(".") for part in rel.parts):
            return None
        return str(rel)

    def on_any_event(self, event):
        if event.is_directory and event.event_type == "modified":
            return
        for raw in filter(None, [getattr(event, "src_path", None),
                                 getattr(event, "dest_path", None)]):
            self._handle(raw, event)

    def _handle(self, raw: str, event):
        rel = self._rel(raw)
        if rel is None:
            return
        p = self.project.root / rel

        if is_artifact(p):
            return

        if p.suffix.lower() == ".pdf":
            if p == self.project.pdf_path and not self.compiler.compiling:
                # compilación externa (fuera de la app): refrescar visor
                self.bus.broadcast_debounced(
                    "pdf", 0.6, lambda: {"type": "pdf_updated", "external": True})
            return

        if event.event_type in ("created", "deleted", "moved") or event.is_directory:
            self.bus.broadcast_debounced(
                "tree", 0.4, lambda: {"type": "tree_changed"})
        if event.event_type in ("modified", "created", "moved") and not event.is_directory:
            def make(rel=rel, p=p):
                ev = {"type": "file_changed", "path": rel}
                try:
                    ev["hash"] = content_hash(p.read_bytes())
                except OSError:
                    ev["hash"] = None
                return ev
            self.bus.broadcast_debounced(f"file:{rel}", 0.25, make)


class ProjectWatcher:
    def __init__(self, project: Project, bus, compiler):
        self.observer = Observer()
        self.observer.schedule(
            _Handler(project, bus, compiler), str(project.root), recursive=True)

    def start(self):
        self.observer.start()

    def stop(self):
        try:
            self.observer.stop()
            self.observer.join(timeout=3)
        except Exception:
            log.exception("al detener el watcher")
