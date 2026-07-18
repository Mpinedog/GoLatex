"""Manejo simple de archivos .bib: listar entradas y agregar nuevas."""
import re

from .project import Project, ProjectError

ENTRY_HEAD = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.MULTILINE)


def _find_bib(project: Project) -> str:
    for name in ("references.bib", "referencias.bib", "bibliography.bib"):
        if (project.root / name).exists():
            return name
    bibs = sorted(project.root.rglob("*.bib"))
    if not bibs:
        raise ProjectError("No hay archivos .bib en el proyecto")
    return project.relpath(bibs[0])


def _field(entry_text: str, field: str) -> str | None:
    m = re.search(rf"\b{field}\s*=\s*", entry_text, re.IGNORECASE)
    if not m:
        return None
    rest = entry_text[m.end():]
    if not rest:
        return None
    if rest[0] == '"':
        end = rest.find('"', 1)
        return rest[1:end].strip() if end > 0 else None
    if rest[0] == "{":
        depth = 0
        for i, ch in enumerate(rest):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return rest[1:i].strip()
        return None
    return rest.split(",")[0].strip() or None


def list_entries(project: Project, bib_file: str | None = None) -> dict:
    rel = bib_file or _find_bib(project)
    text, _, _ = project.read_text(rel)
    entries = []
    heads = list(ENTRY_HEAD.finditer(text))
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        chunk = text[m.start():end]
        entries.append({
            "key": m.group(2),
            "type": m.group(1).lower(),
            "title": _field(chunk, "title"),
            "author": _field(chunk, "author"),
            "year": _field(chunk, "year"),
        })
    return {"file": rel, "entries": entries}


def add_entry(project: Project, entry: str, bib_file: str | None = None) -> dict:
    entry = entry.strip()
    m = ENTRY_HEAD.match(entry)
    if not m:
        raise ProjectError("La entrada debe empezar con @tipo{clave, ...}")
    if entry.count("{") != entry.count("}"):
        raise ProjectError("Llaves desbalanceadas en la entrada BibTeX")
    key = m.group(2)
    rel = bib_file or _find_bib(project)
    text, _, _ = project.read_text(rel)
    existing = {mm.group(2) for mm in ENTRY_HEAD.finditer(text)}
    if key in existing:
        raise ProjectError(f"Ya existe una entrada con clave '{key}' en {rel}")
    new_text = text.rstrip() + "\n\n" + entry + "\n"
    project.write_text(rel, new_text)
    return {"file": rel, "key": key}
