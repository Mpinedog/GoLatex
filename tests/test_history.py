import shutil
import subprocess

import pytest

from server import history
from server.project import Project, ProjectError

pytestmark = pytest.mark.skipif(not shutil.which("git"), reason="git no instalado")


def test_checkpoint(tmp_path, monkeypatch):
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                 "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}.items():
        monkeypatch.setenv(k, v)
    (tmp_path / "main.tex").write_text("hola", encoding="utf-8")
    (tmp_path / "main.aux").write_text("artefacto", encoding="utf-8")
    p = Project(tmp_path)
    with pytest.raises(ProjectError):
        history.checkpoint(p, "sin repo")
    r = history.checkpoint(p, "inicio", init=True)
    assert r["committed"] and not any("main.aux" in f for f in r["files"])
    assert history.checkpoint(p, "otra vez")["committed"] is False
    (tmp_path / "main.tex").write_text("chao", encoding="utf-8")
    history.checkpoint(p, "cambio")
    assert [c["message"] for c in history.log(p)] == ["cambio", "inicio"]
