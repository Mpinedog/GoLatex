"""Detección de texto generado por IA, vía texthumanize (local, sin red).

Convierte el .tex a prosa (sin comandos, matemáticas ni entornos técnicos)
y puntúa el documento completo más cada párrafo. El resultado es orientativo:
ningún detector de IA es concluyente.
"""
import re

from .project import Project, ProjectError

# entornos cuyo contenido no es prosa
DROP_ENVS = (
    "equation", "align", "eqnarray", "gather", "multline", "math",
    "verbatim", "lstlisting", "minted", "tikzpicture", "tabular", "array",
    "algorithm", "algorithmic",
)
# comandos cuyo argumento SÍ es texto que se conserva
KEEP_ARG = (
    "chapter", "section", "subsection", "subsubsection", "paragraph",
    "textbf", "textit", "emph", "texttt", "textsc", "underline", "mbox",
    "caption", "footnote", "title", "author",
)

MIN_PARAGRAPH_WORDS = 30
MAX_PARAGRAPHS = 60

DISCLAIMER = (
    "Heurístico local (texthumanize) y ORIENTATIVO: mide señales estilísticas "
    "(burstiness, repetición, conectores formulaicos…). Ningún detector de IA "
    "es concluyente; un texto humano formal puede puntuar alto y uno de IA "
    "editado puede puntuar bajo. Úsalo como guía de revisión, no como prueba."
)


def latex_to_text(source: str) -> str:
    text = re.sub(r"(?<!\\)%.*", "", source)  # comentarios

    for env in DROP_ENVS:
        text = re.sub(
            rf"\\begin\{{{env}\*?\}}.*?\\end\{{{env}\*?\}}",
            " ", text, flags=re.DOTALL)

    text = re.sub(r"\$\$.*?\$\$", " ", text, flags=re.DOTALL)   # matemática
    text = re.sub(r"\\\[.*?\\\]", " ", text, flags=re.DOTALL)
    text = re.sub(r"\\\(.*?\\\)", " ", text, flags=re.DOTALL)
    text = re.sub(r"(?<!\\)\$[^$\n]*\$", " ", text)

    text = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", text)

    keep = "|".join(KEEP_ARG)
    for _ in range(4):  # anidamiento (\textbf{\emph{...}})
        text, n = re.subn(
            rf"\\(?:{keep})\*?\s*(?:\[[^\]]*\])?\{{([^{{}}]*)\}}", r"\1", text)
        if not n:
            break

    # el resto de comandos se elimina completo, con sus argumentos
    text = re.sub(r"\\[a-zA-Z@]+\*?\s*(?:\[[^\]]*\])?(?:\{[^{}]*\})*", " ", text)
    text = re.sub(r"[{}~]", " ", text)
    text = text.replace(r"\\", " ").replace("\\&", "&").replace("\\%", "%")
    text = re.sub(r"\[[htbpH!]{1,5}\]", " ", text)  # posicionadores de figura
    text = re.sub(r"\s+([.,;:!?)])", r"\1", text)

    # normalizar espacios conservando saltos de párrafo
    paragraphs = [re.sub(r"\s+", " ", p).strip()
                  for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paragraphs if p)


def _preview(paragraph: str, n: int = 12) -> str:
    words = paragraph.split()
    return " ".join(words[:n]) + ("…" if len(words) > n else "")


def analyze(project: Project | None, path: str | None = None,
            text: str | None = None, lang: str = "es") -> dict:
    try:
        from texthumanize import detect_ai
    except ImportError:
        raise ProjectError(
            "Falta la librería 'texthumanize'; instala con: pip install texthumanize")

    if path:
        if not project:
            raise ProjectError("No hay proyecto abierto")
        raw, _, _ = project.read_text(path)
        source_name = path
        prose = latex_to_text(raw) if path.endswith((".tex", ".sty", ".cls")) else raw
    elif text and text.strip():
        source_name = "texto directo"
        prose = latex_to_text(text) if "\\" in text else text
    else:
        raise ProjectError("Indica 'path' (archivo del proyecto) o 'text'")

    prose = prose.strip()
    total_words = len(prose.split())
    if not total_words:
        raise ProjectError(f"{source_name}: no quedó prosa que analizar")

    overall = detect_ai(prose, lang=lang)
    signals = {
        k: round(v, 3)
        for k, v in sorted((overall.get("metrics") or {}).items(),
                           key=lambda kv: -kv[1])
        if isinstance(v, (int, float)) and v > 0
    }

    paragraphs = [p for p in prose.split("\n\n")
                  if len(p.split()) >= MIN_PARAGRAPH_WORDS]
    per_par = []
    for i, p in enumerate(paragraphs[:MAX_PARAGRAPHS], 1):
        r = detect_ai(p, lang=lang)
        per_par.append({
            "n": i,
            "words": len(p.split()),
            "score": round(r["score"], 3),
            "verdict": r["verdict"],
            "preview": _preview(p),
        })
    per_par.sort(key=lambda d: -d["score"])

    result = {
        "source": source_name,
        "lang": lang,
        "words_analyzed": total_words,
        "score": round(overall["score"], 3),           # 0 humano … 1 IA
        "verdict": overall["verdict"],                  # human | mixed | ai
        "confidence": round(overall["confidence"], 3),
        "top_signals": dict(list(signals.items())[:8]),
        "paragraphs_flagged": [d for d in per_par if d["score"] >= 0.6][:10],
        "paragraphs_analyzed": len(per_par),
        "note": DISCLAIMER,
    }
    if len(paragraphs) > MAX_PARAGRAPHS:
        result["truncated"] = (
            f"Solo se puntuaron los primeros {MAX_PARAGRAPHS} párrafos "
            f"de {len(paragraphs)}")
    if total_words < 80:
        result["warning"] = "Texto corto: la señal es poco confiable bajo ~80 palabras"
    return result
