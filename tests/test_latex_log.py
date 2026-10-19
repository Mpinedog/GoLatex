from pathlib import Path

from server.latex_log import parse_blg, parse_log

LOG = """\
(./main.tex
(./cap/c1.tex
./cap/c1.tex:2: Undefined control sequence.
l.2 \\comandoinexistente

)
LaTeX Warning: Citation `x' on page 1 undefined on input line 6.
Output written on main.pdf (3 pages, 1234 bytes).
"""


def test_error_con_archivo_y_linea():
    r = parse_log(LOG, Path("/proyecto"))
    assert r["errors"][0]["file"] == "cap/c1.tex"
    assert r["errors"][0]["line"] == 2
    assert "Undefined control sequence" in r["errors"][0]["message"]
    assert r["pages"] == 3


def test_warning_atribuido_al_archivo_activo():
    r = parse_log(LOG, Path("/proyecto"))
    w = r["warnings"][0]
    assert w["file"] == "main.tex" and w["line"] == 6


def test_ruta_absoluta_windows_en_error():
    log = "C:/Users/x/tesis/cap/c2.tex:7: Missing $ inserted.\nl.7 x\n"
    r = parse_log(log, None)
    assert r["errors"][0]["file"] == "C:/Users/x/tesis/cap/c2.tex"
    assert r["errors"][0]["line"] == 7


def test_biber():
    blg = ("[0] Config.pm:311> INFO - This is Biber 2.19\n"
           "[57] Biber.pm:131> WARN - I didn't find a database entry for 'foo'\n"
           "[60] Utils.pm:1> ERROR - BibTeX subsystem: refs.bib, line 3, syntax error\n")
    items = parse_blg(blg)
    assert [i["type"] for i in items] == ["warning", "error"]
    assert "foo" in items[0]["message"]


def test_bibtex():
    items = parse_blg("Warning--I didn't find a database entry for \"bar\"\n")
    assert items[0]["type"] == "warning" and "bar" in items[0]["message"]
