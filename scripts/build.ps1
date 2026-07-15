[CmdletBinding()]
param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
$python = Join-Path $repo ".venv\Scripts\python.exe"

$migrationFiles = Get-ChildItem "$repo\migrations" -Filter "*.sql" -File
if ($migrationFiles.Count -eq 0) { throw "Tidak ada berkas migrasi SQL untuk dibundel." }
$pyInstallerArgs = @(
    "--noconfirm", "--clean", "--windowed", "--onedir", "--name", "DifferentNetworkTranscribe",
    "--collect-all", "numpy", "--collect-all", "faster_whisper", "--collect-all", "ctranslate2",
    "--collect-all", "av", "--collect-all", "PySide6"
)
foreach ($migration in $migrationFiles) {
    # Add each SQL file explicitly. Passing the directory proved unreliable in
    # the frozen one-folder layout and resulted in an empty migrations folder.
    $pyInstallerArgs += "--add-data"
    $pyInstallerArgs += "$($migration.FullName);migrations"
}
$pyInstallerArgs += "app\main.py"
& $python -m PyInstaller @pyInstallerArgs
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
