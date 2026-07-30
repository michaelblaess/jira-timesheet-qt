# ============================================================
#  jira-timesheet-qt - Installer (PowerShell)
#
#  Verwendung:
#    irm https://raw.githubusercontent.com/michaelblaess/jira-timesheet-qt/main/install.ps1 | iex
#
#  Laedt den Quellcode des neuesten Release, erstellt ein venv und installiert
#  alle Dependencies (inkl. PySide6). Voraussetzung: Python 3.12+.
#
#  Installiert nach: %LOCALAPPDATA%\jira-timesheet-qt\
#  Erstellt Wrapper:  %LOCALAPPDATA%\jira-timesheet-qt\bin\jira-timesheet-qt.cmd
#
#  Hinweis: fuer die fertigen Standalone-Binaries (ohne Python) stattdessen das
#  Archiv unter Releases herunterladen und entpacken.
# ============================================================

$ErrorActionPreference = "Stop"

$Repo = "michaelblaess/jira-timesheet-qt"
$InstallDir = Join-Path $env:LOCALAPPDATA "jira-timesheet-qt"
$BinDir = Join-Path $InstallDir "bin"
$Wrapper = Join-Path $BinDir "jira-timesheet-qt.cmd"

Write-Host ""
Write-Host "  +================================================+" -ForegroundColor Cyan
Write-Host "  |   jira-timesheet-qt - Installer                 |" -ForegroundColor Cyan
Write-Host "  +================================================+" -ForegroundColor Cyan
Write-Host ""

# --- Python pruefen (3.12+) ---
$PythonCmd = $null
foreach ($cmd in @("python", "python3", "py")) {
    try {
        $ver = & $cmd --version 2>&1
        if ($ver -match "Python 3\.(\d+)") {
            $minor = [int]$Matches[1]
            if ($minor -ge 12) {
                $PythonCmd = $cmd
                Write-Host "  [OK] $ver gefunden ($cmd)" -ForegroundColor Green
                break
            }
        }
    } catch {}
}

if (-not $PythonCmd) {
    Write-Host "  [FEHLER] Python 3.12+ nicht gefunden!" -ForegroundColor Red
    Write-Host "  Bitte installieren: https://python.org"
    exit 1
}
Write-Host ""

# --- Neuestes Release ermitteln ---
Write-Host "  Suche neuestes Release..."
$ApiUrl = "https://api.github.com/repos/${Repo}/releases/latest"

try {
    $Release = Invoke-RestMethod -Uri $ApiUrl -UseBasicParsing
    $Version = $Release.tag_name
    $ZipUrl = $Release.zipball_url
    Write-Host "  [OK] Release: $Version" -ForegroundColor Green
} catch {
    Write-Host "  [WARNUNG] Kein Release gefunden, verwende main-Branch" -ForegroundColor Yellow
    $Version = "main"
    $ZipUrl = "https://github.com/${Repo}/archive/refs/heads/main.zip"
}
Write-Host ""

# --- Download ---
$TmpDir = Join-Path $env:TEMP "jira-timesheet-qt-install"
if (Test-Path $TmpDir) { Remove-Item -Recurse -Force $TmpDir }
New-Item -ItemType Directory -Path $TmpDir -Force | Out-Null
$TmpFile = Join-Path $TmpDir "source.zip"

Write-Host "  Lade Quellcode herunter..."
try {
    Invoke-WebRequest -Uri $ZipUrl -OutFile $TmpFile -UseBasicParsing
} catch {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    (New-Object System.Net.WebClient).DownloadFile($ZipUrl, $TmpFile)
}
Write-Host "  [OK] Download abgeschlossen" -ForegroundColor Green
Write-Host ""

# --- Entpacken (venv sichern) ---
Write-Host "  Entpacke nach: $InstallDir"
$VenvBackup = $null
if (Test-Path $InstallDir) {
    $VenvPath = Join-Path $InstallDir ".venv"
    if (Test-Path $VenvPath) {
        $VenvBackup = Join-Path $env:TEMP "jira-timesheet-qt-venv-bak"
        if (Test-Path $VenvBackup) { Remove-Item -Recurse -Force $VenvBackup }
        Move-Item $VenvPath $VenvBackup
    }
    Remove-Item -Recurse -Force $InstallDir -Exclude ".venv"
}

New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null
Expand-Archive -Path $TmpFile -DestinationPath $TmpDir -Force

$SubDir = Get-ChildItem -Path $TmpDir -Directory | Where-Object { $_.Name -ne "source.zip" } | Select-Object -First 1
if ($SubDir) {
    Get-ChildItem -Path $SubDir.FullName | Move-Item -Destination $InstallDir -Force
}

if ($VenvBackup -and (Test-Path $VenvBackup)) {
    Move-Item $VenvBackup (Join-Path $InstallDir ".venv")
}

Remove-Item -Recurse -Force $TmpDir
Write-Host "  [OK] Entpackt" -ForegroundColor Green
Write-Host ""

# --- venv + Dependencies ---
$VenvPython = Join-Path $InstallDir ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "  Erstelle Python venv..."
    & $PythonCmd -m venv (Join-Path $InstallDir ".venv")
}

# pip.ini fuer Corporate-Proxy/Corporate Proxy
$PipIni = Join-Path $InstallDir ".venv\pip.ini"
if (-not (Test-Path $PipIni)) {
    Set-Content -Path $PipIni -Value "[global]`ntrusted-host = pypi.org pypi.python.org files.pythonhosted.org"
}

Write-Host "  Installiere Dependencies (inkl. PySide6, kann etwas dauern)..."
& $VenvPython -m pip install --upgrade pip --quiet 2>$null
& (Join-Path $InstallDir ".venv\Scripts\pip.exe") install -e $InstallDir --quiet 2>$null
Write-Host "  [OK] Dependencies installiert" -ForegroundColor Green
Write-Host ""

# --- Wrapper erstellen ---
New-Item -ItemType Directory -Path $BinDir -Force | Out-Null

$WrapperContent = @"
@echo off
REM jira-timesheet-qt - Wrapper (automatisch generiert)
start "" "$(Join-Path $InstallDir '.venv\Scripts\pythonw.exe')" -m jira_timesheet_qt %*
"@
Set-Content -Path $Wrapper -Value $WrapperContent -Encoding ASCII
Write-Host "  [OK] Wrapper erstellt" -ForegroundColor Green

# --- PATH pruefen ---
$UserPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($UserPath -notlike "*$BinDir*") {
    Write-Host ""
    Write-Host "  Fuege zum PATH hinzu: $BinDir" -ForegroundColor Yellow
    [Environment]::SetEnvironmentVariable("Path", "$BinDir;$UserPath", "User")
    $env:Path = "$BinDir;$env:Path"
    Write-Host "  [OK] PATH aktualisiert" -ForegroundColor Green
}

# --- Fertig ---
Write-Host ""
Write-Host "  +================================================+" -ForegroundColor Green
Write-Host "  |   Installation abgeschlossen! ($Version)" -ForegroundColor Green
Write-Host "  +================================================+" -ForegroundColor Green
Write-Host ""
Write-Host "  Starten mit:"
Write-Host "    jira-timesheet-qt" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Beim ersten Start den Haftungshinweis bestaetigen, dann den"
Write-Host "  Jira-Zugang in den Einstellungen (Strg+,) hinterlegen."
Write-Host ""
Write-Host "  Aktualisieren:  Installer erneut ausfuehren." -ForegroundColor Gray
Write-Host "  Deinstallieren: Remove-Item -Recurse '$InstallDir'" -ForegroundColor Gray
Write-Host ""
Write-Host "  HINWEIS: Oeffne ein neues Terminal, damit der PATH wirkt." -ForegroundColor Yellow
Write-Host ""
