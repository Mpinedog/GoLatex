@echo off
rem Doble clic para abrir GoLatex (llama a run.ps1 sin pelear con la ExecutionPolicy)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
