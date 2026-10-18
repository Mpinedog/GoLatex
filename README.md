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

- Python 3.11+.
- Una distribución TeX con `latexmk` y `synctex`:
  - **macOS**: MacTeX (`/Library/TeX/texbin`).
  - **Windows**: MiKTeX + Strawberry Perl (latexmk es un script de Perl):
    ```powershell
    winget install MiKTeX.MiKTeX --scope user
    winget install StrawberryPerl.StrawberryPerl
    # que MiKTeX instale solo los paquetes que falten, sin ventanas:
    initexmf --set-config-value="[MPM]AutoInstall=1"
    ```
    TeX Live para Windows también sirve (trae Perl incluido).
  - **Linux**: TeX Live (`latexmk`, `synctex`).

GoLatex busca los binarios en el `PATH` y en las rutas típicas de cada
sistema; si los tienes en otro lado, define `GOLATEX_TEXBIN` con esa carpeta.

## Arrancar

macOS / Linux:

```bash
./run.sh                      # abre http://localhost:8123 (último proyecto)
./run.sh /ruta/a/mi/proyecto  # abre esa carpeta directamente
```

Windows (PowerShell, o doble clic en `run.bat`):

```powershell
.\run.bat                      # último proyecto
.\run.bat C:\ruta\a\mi\tesis   # abre esa carpeta
```

La primera vez crea `.venv` e instala dependencias. Puerto configurable con
`GOLATEX_PORT`. El servidor escucha solo en `127.0.0.1`.

## Motor de compilación

Selector ⚙ junto al archivo principal: `auto`, `pdflatex`, `xelatex` o
`lualatex` (se recuerda por proyecto). En `auto` se usa el comentario mágico
`% !TEX program = xelatex` si existe; si no, `xelatex` cuando el principal carga
`fontspec`, `unicode-math` o `polyglossia`, y `pdflatex` en otro caso. Los
errores y warnings de BibTeX **y de biber** (`biblatex`) aparecen en el panel.

## Uso (cara humana)

- **Abrir proyecto**: botón 📁 (recientes o explorador de carpetas).
- **Editar**: clic en un `.tex`/`.bib` del árbol. `⌘S` / `Ctrl+S` guarda. Pestañas con
  indicador de cambios sin guardar.
- **Compilar**: botón ▶ o `⌘⏎` / `Ctrl+Enter` (raíz configurable con el selector ★; por
  defecto `main.tex`). El visor PDF se refresca manteniendo página y zoom.
- **Problemas**: panel inferior con errores/warnings clicables (saltan al
  código); pestaña "Log crudo" con el log completo.
- **SyncTeX**: `⌥`+clic (`Alt`+clic en Windows) (o doble clic) sobre el PDF salta a la línea de
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
| `project_info` | raíz, main, motor, lista de `\input`, ¿PDF al día?, páginas |
| `set_engine` | fija el motor: `pdflatex`, `xelatex`, `lualatex` o `auto` |
| `list_files` | árbol del proyecto (sin artefactos) |
| `read_file` / `write_file` | leer / escribir un archivo |
| `edit_file` | reemplazo puntual (old → new, con control de unicidad) |
| `compile` | latexmk; devuelve ok, errores parseados (archivo, línea, mensaje) y páginas |
| `get_log` | log crudo completo, bajo demanda |
| `render_page` | página N del PDF como imagen PNG (para *ver* el resultado) |
| `search` | grep (regex) sobre los archivos de texto del proyecto |
| `bib_list` / `bib_add` | listar / agregar entradas de `references.bib` |
| `ai_check` | estima qué tan "IA" suena un `.tex` del proyecto (o texto directo): score 0–1, párrafos sospechosos y señales (detector local [texthumanize](https://github.com/ksanyok/TextHumanize), sin red). Orientativo: ningún detector de IA es concluyente |

Ejemplo de sesión con el agente: *"agrega un typo deliberado en
capitulo_4.tex, compílalo, léeme el error, arréglalo y recompila"* — cada
cambio y compilación se ve en vivo en la app.

Nota: el MCP opera sobre el proyecto **abierto en la app** (una sola sesión y
cola de compilación compartida: si el humano y el agente compilan a la vez, se
encolan y no se pisan).

## Estructura

```
run.sh            arranque macOS/Linux (venv + uvicorn + abrir navegador)
run.ps1 / run.bat arranque Windows
server/           FastAPI: REST + WebSocket + watcher + MCP (/mcp)
web/              UI estática: CodeMirror + PDF.js (vendorizados)
```
