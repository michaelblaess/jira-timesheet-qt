#Requires -Version 5.1
<#
.SYNOPSIS
    Compiles jira-timesheet-qt into a standalone Windows binary with Nuitka.

.DESCRIPTION
    Produces a self-contained --standalone build (no Python install needed on
    the target machine). Output: dist\jira-timesheet-qt\jira-timesheet-qt.exe
    plus its DLLs, and a zipped dist\jira-timesheet-qt-vX.Y.Z-win64.zip.

    --standalone (Ordner), NICHT --onefile: nur der Ordner-Build erfuellt die
    LGPL-Weitergabepflicht von PySide6 (Qt-DLLs als eigene Dateien daneben).
#>

$ErrorActionPreference = "Stop"

$root    = $PSScriptRoot
$entry   = Join-Path $root "src\jira_timesheet_qt\__main__.py"
$initPy  = Join-Path $root "src\jira_timesheet_qt\__init__.py"
$icon    = Join-Path $root "assets\app-icon.ico"
$outDir  = Join-Path $root "dist"
$distDir = Join-Path $outDir "jira-timesheet-qt"

# venv-Python bevorzugen, sonst System-Python
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

# venv mit dem Lockfile abgleichen, damit Nuitka keine veralteten Dependencies
# einkompiliert. --inexact laesst Extra-Pakete wie das ad-hoc installierte
# nuitka unangetastet.
if (Get-Command uv -ErrorAction SilentlyContinue) {
    Write-Host "Syncing venv to lockfile (uv sync --inexact)..." -ForegroundColor Cyan
    & uv sync --inexact --project $root
    if ($LASTEXITCODE -ne 0) { throw "uv sync fehlgeschlagen" }
} else {
    Write-Host "uv nicht gefunden - venv-Sync uebersprungen" -ForegroundColor Yellow
}

# Version aus __init__.py lesen, damit die EXE-Metadaten nicht von pyproject driften
$version = ([regex]'__version__\s*=\s*"([^"]+)"').Match((Get-Content -Raw $initPy)).Groups[1].Value
if (-not $version) { throw "Konnte __version__ nicht aus $initPy lesen" }

Write-Host "Compiling jira-timesheet-qt v$version with Nuitka..." -ForegroundColor Cyan

if (Test-Path $distDir) { Remove-Item -Recurse -Force $distDir }

$started = Get-Date

# Nuitka als Build-Tool sicherstellen (kein Dev-Dep, ad-hoc installiert).
& $python -m nuitka --version 2>$null 1>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka fehlt im venv - installiere..." -ForegroundColor Yellow
    & uv pip install nuitka
    if ($LASTEXITCODE -ne 0) { throw "Nuitka-Installation fehlgeschlagen" }
}

# --enable-plugin=pyside6            : Qt-Binding samt Plugins korrekt buendeln
# --windows-console-mode=disable     : GUI-App, kein schwarzes Konsolenfenster
# --include-package-data=qtawesome   : die Material-Design-Icon-Fonts (Paketdaten)
# --include-package=holidays         : holidays laedt Laender-Module dynamisch
& $python -m nuitka `
    --standalone `
    --assume-yes-for-downloads `
    --remove-output `
    --enable-plugin=pyside6 `
    --windows-console-mode=disable `
    --include-package=jira_timesheet_qt `
    --include-package-data=jira_timesheet_qt `
    --include-package-data=qtawesome `
    --include-package=holidays `
    --windows-icon-from-ico=$icon `
    --output-dir=$outDir `
    --output-filename=jira-timesheet-qt.exe `
    --company-name="Michael Blaess" `
    --product-name="jira-timesheet-qt" `
    --file-version=$version `
    --product-version=$version `
    $entry

if ($LASTEXITCODE -ne 0) { throw "Nuitka-Build fehlgeschlagen (Exit $LASTEXITCODE)" }

# Nuitka benennt den dist-Ordner nach dem Hauptmodul (__main__.dist) - umbenennen
$nuitkaDist = Join-Path $outDir "__main__.dist"
if (Test-Path $nuitkaDist) { Rename-Item -Path $nuitkaDist -NewName "jira-timesheet-qt" }

$elapsed = [int]((Get-Date) - $started).TotalSeconds
$exe     = Join-Path $distDir "jira-timesheet-qt.exe"
$sizeMB  = [math]::Round(((Get-ChildItem -Recurse $distDir | Measure-Object Length -Sum).Sum) / 1MB, 1)

$zip = Join-Path $outDir "jira-timesheet-qt-v$version-win64.zip"
if (Test-Path $zip) { Remove-Item -Force $zip }
Compress-Archive -Path $distDir -DestinationPath $zip
$zipMB = [math]::Round((Get-Item $zip).Length / 1MB, 1)

Write-Host ""
Write-Host "Done in ${elapsed}s" -ForegroundColor Green
Write-Host "  dist folder : $distDir  (${sizeMB} MB)"
Write-Host "  zip         : $zip  (${zipMB} MB)"
Write-Host "  run         : $exe"
