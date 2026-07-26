#Requires -Version 5.1
<#
.SYNOPSIS
    Richtet die Entwicklungsumgebung ein (venv, Abhaengigkeiten, Nuitka).
#>
$ErrorActionPreference = "Stop"

# Hinter einem TLS-aufbrechenden Proxy kennt uv die Firmen-Wurzel nicht.
$env:UV_NATIVE_TLS = "1"
$env:SSL_CERT_FILE = $null

Write-Host "Abhaengigkeiten synchronisieren..." -ForegroundColor Cyan
uv sync --extra dev
if ($LASTEXITCODE -ne 0) { throw "uv sync fehlgeschlagen" }

Write-Host "Nuitka bereitstellen..." -ForegroundColor Cyan
uv pip install nuitka
if ($LASTEXITCODE -ne 0) { throw "Nuitka-Installation fehlgeschlagen" }

Write-Host ""
Write-Host "Fertig. Starten mit:  .\run.ps1" -ForegroundColor Green
Write-Host "Mit Beispieldaten:    .\run.ps1 --demo" -ForegroundColor Green
