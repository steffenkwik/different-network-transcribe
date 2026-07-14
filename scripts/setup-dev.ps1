<#
.SYNOPSIS
    One-time developer setup. End users never run this: they use the installer.
#>
[CmdletBinding()]
param(
    [string]$PythonExe = "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

if (-not (Test-Path $PythonExe)) {
    throw "Python 3.12 tidak ditemukan di $PythonExe. Pasang dengan: winget install Python.Python.3.12"
}

$version = & $PythonExe --version
if ($version -notmatch "3\.12\.") {
    throw "Butuh Python 3.12.x, ditemukan: $version"
}

Write-Host "== membuat virtual environment ==" -ForegroundColor Cyan
& $PythonExe -m venv .venv

$python = Join-Path $repo ".venv\Scripts\python.exe"
& $python -m pip install --upgrade pip
& $python -m pip install -r requirements-lock.txt

Write-Host "`nSetup selesai. Jalankan: scripts\test.ps1" -ForegroundColor Green
