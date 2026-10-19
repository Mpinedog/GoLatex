import pytest

pytest.importorskip("httpx")
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    # un solo TestClient por módulo: el gestor de sesiones MCP solo puede
    # arrancar una vez por proceso
    mp = pytest.MonkeyPatch()
    home = tmp_path_factory.mktemp("home")
    mp.setenv("HOME", str(home))
    mp.setenv("USERPROFILE", str(home))
    from server import config
    mp.setattr(config, "CONFIG_DIR", home / ".golatex")
    mp.setattr(config, "CONFIG_FILE", home / ".golatex" / "state.json")
    proj = tmp_path_factory.mktemp("tesis")
    (proj / "main.tex").write_text("\\documentclass{article}\n", encoding="utf-8")
    from server.state import STATE
    STATE.open_project(str(proj))
    from server.main import app
    with TestClient(app, base_url="http://localhost:8123") as c:
        yield c
    STATE.close_project()
    mp.undo()


def test_rechaza_otro_host(client):
    assert client.get("/api/tree").status_code == 200
    assert client.get("/api/tree", headers={"host": "evil.com"}).status_code == 400


def test_guardado_con_conflicto_responde_409(client):
    f = client.get("/api/file", params={"path": "main.tex"}).json()
    ok = client.put("/api/file", json={"path": "main.tex", "content": "a",
                                       "base_hash": f["hash"]})
    assert ok.status_code == 200
    stale = client.put("/api/file", json={"path": "main.tex", "content": "b",
                                          "base_hash": f["hash"]})
    assert stale.status_code == 409 and stale.json()["hash"] == ok.json()["hash"]


def test_motor(client):
    assert client.post("/api/engine", json={"engine": "xelatex"}).json()["engine"] == "xelatex"
    assert client.post("/api/engine", json={"engine": "auto"}).json()["engine_setting"] is None
    assert client.post("/api/engine", json={"engine": "word"}).status_code == 400
