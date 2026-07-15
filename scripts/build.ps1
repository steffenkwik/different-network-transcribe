[CmdletBinding()]
param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$python = Join-Path $repo ".venv\Scripts\python.exe"

& $python -m PyInstaller --noconfirm --clean --windowed --onedir --name DifferentNetworkTranscribe --add-data "migrations;migrations" --collect-all numpy --collect-all faster_whisper --collect-all ctranslate2 --collect-all av --collect-all PySide6 app\main.py
if ($LASTEXITCODE -ne 0) { throw "PyInstaller gagal" }

$iscc = Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"
if (-not (Test-Path $iscc)) { throw "Inno Setup tidak ditemukan" }
& $iscc installer\different-network-transcribe.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup gagal" }

New-Item -ItemType Directory -Force release | Out-Null
Compress-Archive -Path dist\DifferentNetworkTranscribe\* -DestinationPath release\DifferentNetworkTranscribe-Portable-x64.zip -Force
Get-ChildItem release -File |
    Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
    Get-FileHash -Algorithm SHA256 |
    ForEach-Object { "{0}  {1}" -f $_.Hash, $_.Path.Name } |
    Set-Content release\SHA256SUMS.txt -Encoding utf8

if (-not $SkipSmokeTest) {
    & "$PSScriptRoot\smoke-test.ps1" -Artifact All
    if ($LASTEXITCODE -ne 0) { throw "Smoke test packaging gagal" }
}
