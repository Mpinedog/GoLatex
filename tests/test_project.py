import pytest

from server.project import ConflictError, Project, ProjectError


@pytest.fixture
def proj(tmp_path):
    (tmp_path / "caps" / "sub").mkdir(parents=True)
    (tmp_path / "main.tex").write_text(
        "\\documentclass{article}\n\\begin{document}\n"
        "\\include{caps/c1}\n% \\input{comentado}\n\\subfile{caps/c2.tex}\n"
        "\\import{caps/}{c3}\n\\end{document}\n", encoding="utf-8")
    (tmp_path / "caps" / "c1.tex").write_text("\\subimport{sub/}{d1}\n", encoding="utf-8")
    for f in ("caps/c2.tex", "caps/c3.tex", "caps/sub/d1.tex", "comentado.tex"):
        (tmp_path / f).write_text("", encoding="utf-8")
    return Project(tmp_path)


def test_rutas_siempre_con_slash(proj):
    paths = [n["path"] for n in proj.tree() if n["type"] == "dir"]
    assert paths == ["caps"]
    sub = next(n for n in proj.tree() if n["name"] == "caps")["children"]
    assert all("\\" not in n["path"] for n in sub)


def test_inputs_recursivos(proj):
    assert proj.inputs() == ["caps/c1.tex", "caps/sub/d1.tex", "caps/c2.tex", "caps/c3.tex"]


def test_no_sale_del_proyecto(proj):
    with pytest.raises(ProjectError):
        proj.resolve("../fuera.tex")


def test_motor_auto(proj):
    assert proj.engine == "pdflatex"
    proj.main_path.write_text("\\documentclass{article}\n\\usepackage{fontspec}\n", encoding="utf-8")
    assert proj.engine == "xelatex"
    proj.main_path.write_text("% !TEX program = lualatex\n\\documentclass{article}\n",
                              encoding="utf-8")
    assert proj.engine == "lualatex"
    proj.set_engine("pdflatex")
    assert proj.engine == "pdflatex"
    with pytest.raises(ProjectError):
        proj.set_engine("word")


def test_guardado_detecta_conflicto(proj):
    _, h, _ = proj.read_text("caps/c2.tex")
    proj.write_text("caps/c2.tex", "versión del agente")       # otro escribe
    with pytest.raises(ConflictError):
        proj.write_text("caps/c2.tex", "versión del humano", expected_hash=h)
    assert proj.read_text("caps/c2.tex")[0] == "versión del agente"


def test_escritura_atomica_sin_temporales(proj):
    proj.write_text("caps/nuevo.tex", "ñandú")
    assert proj.read_text("caps/nuevo.tex")[0] == "ñandú"
    assert not list(proj.root.rglob("*.golatex-tmp"))
