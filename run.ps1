#Requires -Version 5.1
<#
.SYNOPSIS
    Startet die Anwendung aus dem Quellcode.
.EXAMPLE
    .\run.ps1 --demo
#>
$ErrorActionPreference = "Stop"

$venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

& $python -m jira_timesheet_qt @args
exit $LASTEXITCODE
