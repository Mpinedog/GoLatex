"""Estado compartido entre la app (REST/WS) y el servidor MCP.

Un único proyecto abierto a la vez; ambas caras (humana y agéntica) operan
sobre estas mismas instancias, así que comparten cola de compilación y
eventos en vivo.
"""
import time
from pathlib import Path

from .compiler import Compiler
from .config import load_config, save_config
from .events import EventBus
from .project import Project, ProjectError
from .watcher import ProjectWatcher


class AppState:
    def __init__(self):
        self.bus = EventBus()
        self.project: Project | None = None
        self.compiler: Compiler | None = None
        self.watcher: ProjectWatcher | None = None
        self.config = load_config()

    def require_project(self) -> Project:
        if not self.project:
            raise ProjectError(
                "No hay proyecto abierto. Abre una carpeta en la app "
                "(http://localhost:8123) o con open_project.")
        return self.project

    def open_project(self, path: str) -> Project:
        try:
            key = str(Path(path).expanduser().resolve())
        except OSError:
            key = str(path)
        project = Project(path)  # valida la carpeta antes de cerrar la actual
        remembered = next(
            (r for r in self.config["recents"] if r["path"] == key), None)
        if remembered:
            try:
                project.set_engine(remembered.get("engine"))
            except ProjectError:
                pass
            main = remembered.get("main")
            if main and (project.root / main).is_file():
                project.main = main
        self.close_project()
        self.project = project
        self.compiler = Compiler(project, self.bus)
        self.watcher = ProjectWatcher(project, self.bus, self.compiler)
        self.watcher.start()
        self._remember()
        self.bus.broadcast({"type": "project_opened", "root": str(project.root),
                            "main": project.main})
        return project

    def close_project(self):
        if self.watcher:
            self.watcher.stop()
        self.watcher = None
        self.project = None
        self.compiler = None

    def set_main(self, rel: str):
        project = self.require_project()
        project.set_main(rel)
        self._remember()
        self.bus.broadcast({"type": "main_changed", "path": project.main})

    def set_engine(self, engine: str | None):
        project = self.require_project()
        project.set_engine(engine)
        self._remember()
        self.bus.broadcast({"type": "engine_changed", "setting": project.engine_setting,
                            "engine": project.engine})

    def _remember(self):
        if not self.project:
            return
        entry = {"path": str(self.project.root), "main": self.project.main,
                 "engine": self.project.engine_setting, "opened_at": time.time()}
        recents = [r for r in self.config["recents"]
                   if r["path"] != entry["path"]]
        self.config["recents"] = [entry, *recents][:10]
        save_config(self.config)


STATE = AppState()
