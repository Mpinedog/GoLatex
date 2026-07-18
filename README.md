# GoLatex

Workspace LaTeX local con dos caras sobre el mismo motor:

- **Humana**: app tipo Overleaf local — árbol de archivos, editor con resaltado
  LaTeX y visor PDF con SyncTeX, todo en el navegador.
- **Agéntica**: servidor **MCP** que expone el proyecto abierto (leer/escribir
  archivos, compilar con errores parseados, ver páginas del PDF como imagen)
  para Claude Code u otro cliente MCP. Ambas caras comparten proyecto, cola de
  compilación y eventos en vivo: lo que escribe el agente aparece al instante
  en la app.

Todo local: sin base de datos, sin cuentas, sin nube.

## Requisitos

- macOS con TeX Live en `/Library/TeX/texbin` (`latexmk`, `synctex`).
- Python 3.11+.

## Arrancar

```bash
./run.sh                      # abre http://localhost:8123 (último proyecto)
./run.sh /ruta/a/mi/proyecto  # abre esa carpeta directamente
```

La primera vez crea `.venv` e instala dependencias. Puerto configurable con
`GOLATEX_PORT`.

## Uso (cara humana)

- **Abrir proyecto**: botón 📁 (recientes o explorador de carpetas).
- **Editar**: clic en un `.tex`/`.bib` del árbol. `⌘S` guarda. Pestañas con
  indicador de cambios sin guardar.
- **Compilar**: botón ▶ o `⌘⏎` (raíz configurable con el selector ★; por
  defecto `main.tex`). El visor PDF se refresca manteniendo página y zoom.
- **Problemas**: panel inferior con errores/warnings clicables (saltan al
  código); pestaña "Log crudo" con el log completo.
- **SyncTeX**: `⌥`+clic (o doble clic) sobre el PDF salta a la línea de
  código; `⌘⌥J` en el editor salta del código al PDF.
- **Auto**: casilla "auto" recompila con cada guardado. 🌙 alterna modo oscuro.
- **Árbol**: clic derecho para crear/renombrar/eliminar (va a la Papelera) y
  fijar el `.tex` principal.

Si un agente (u otro editor) modifica un archivo, el editor lo recarga al
instante; si tenías cambios sin guardar, aparece un aviso para decidir. Si se
recompila, el PDF se actualiza solo.

## Conectar el MCP a Claude Code (cara agéntica)

Con la app corriendo (`./run.sh`):

```bash
claude mcp add --transport http golatex http://localhost:8123/mcp
```

Para Claude Desktop u otros clientes, registra la URL `http://localhost:8123/mcp`
(transporte Streamable HTTP).

Herramientas expuestas (siempre restringidas a la carpeta del proyecto abierto):

| Tool | Qué hace |
|---|---|
| `project_info` | raíz, main, lista de `\input`, ¿PDF al día?, páginas |
| `list_files` | árbol del proyecto (sin artefactos) |
| `read_file` / `write_file` | leer / escribir un archivo |
| `edit_file` | reemplazo puntual (old → new, con control de unicidad) |
| `compile` | latexmk; devuelve ok, errores parseados (archivo, línea, mensaje) y páginas |
| `get_log` | log crudo completo, bajo demanda |
| `render_page` | página N del PDF como imagen PNG (para *ver* el resultado) |
| `search` | grep (regex) sobre los archivos de texto del proyecto |
| `bib_list` / `bib_add` | listar / agregar entradas de `references.bib` |

Ejemplo de sesión con el agente: *"agrega un typo deliberado en
capitulo_4.tex, compílalo, léeme el error, arréglalo y recompila"* — cada
cambio y compilación se ve en vivo en la app.

Nota: el MCP opera sobre el proyecto **abierto en la app** (una sola sesión y
cola de compilación compartida: si el humano y el agente compilan a la vez, se
encolan y no se pisan).

## Estructura

```
run.sh            arranque (venv + uvicorn + abrir navegador)
server/           FastAPI: REST + WebSocket + watcher + MCP (/mcp)
web/              UI estática: CodeMirror + PDF.js (vendorizados)
```
