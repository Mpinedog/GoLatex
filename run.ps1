# GoLatex en Windows: crea el entorno, instala dependencias y abre la app.
#   .\run.ps1                       -> último proyecto abierto
#   .\run.ps1 C:\ruta\a\mi\tesis    -> abre esa carpeta
param([string]$Project = "")
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath $PSScriptRoot

$port = if ($env:GOLATEX_PORT) { $env:GOLATEX_PORT } else { "8123" }
$py = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"

if (-not (Test-Path $py)) {
    Write-Host "Creando entorno virtual (.venv)..."
    if (Get-Command py -ErrorAction SilentlyContinue) { py -3 -m venv .venv } else { python -m venv .venv }
}

# Reinstala dependencias solo si requirements.txt cambió
$stamp = ".venv\.requirements.sha256"
$hash = (Get-FileHash requirements.txt -Algorithm SHA256).Hash
if (-not (Test-Path $stamp) -or (Get-Content $stamp) -ne $hash) {
    Write-Host "Instalando dependencias..."
    & $py -m pip install --disable-pip-version-check -q -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "Falló pip install" }
    Set-Content $stamp $hash
}

if ($Project) { $env:GOLATEX_OPEN = (Resolve-Path -LiteralPath $Project).Path }

# Abre el navegador cuando el servidor ya responde
Start-Job -ArgumentList $port -ScriptBlock {
    param($p)
    for ($i = 0; $i -lt 40; $i++) {
        try { Invoke-WebRequest "http://localhost:$p/api/state" -UseBasicParsing -TimeoutSec 1 | Out-Null; break }
        catch { Start-Sleep -Milliseconds 500 }
    }
    Start-Process "http://localhost:$p"
} | Out-Null

Write-Host "GoLatex en http://localhost:$port  (Ctrl+C para cerrar)"
& $py -m uvicorn server.main:app --host 127.0.0.1 --port $port
