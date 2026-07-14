<#
.SYNOPSIS
    Quality gate: lint, type-check, then the test suite.
.DESCRIPTION
    scripts\test.ps1            full suite
    scripts\test.ps1 -Fast      skip slow lanes (13k perf, real model)
    scripts\test.ps1 -Acceptance   only the mandatory addendum 23-25 scenarios
    Real private data (marker: realdata) never runs here. It is Phase 13 only.
#>
[CmdletBinding()]
param(
    [switch]$Fast,
    [switch]$Acceptance
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Virtual environment tidak ditemukan. Jalankan scripts\setup-dev.ps1 terlebih dahulu."
}

Write-Host "== ruff ==" -ForegroundColor Cyan
& $python -m ruff check app worker tests
if ($LASTEXITCODE -ne 0) { throw "ruff gagal" }

Write-Host "== mypy ==" -ForegroundColor Cyan
& $python -m mypy app worker
if ($LASTEXITCODE -ne 0) { throw "mypy gagal" }

Write-Host "== pytest ==" -ForegroundColor Cyan
$markers = "not realdata"
if ($Fast)       { $markers = "not realdata and not slow and not realmodel" }
if ($Acceptance) { $markers = "acceptance and not realdata" }

& $python -m pytest -m $markers
if ($LASTEXITCODE -ne 0) { throw "pytest gagal" }

Write-Host "== private-data scan ==" -ForegroundColor Cyan
& $python scripts\scan_private_data.py
if ($LASTEXITCODE -ne 0) { throw "data privat terdeteksi" }

Write-Host "`nQuality gate PASSED" -ForegroundColor Green
