[CmdletBinding()]
param(
    [switch]$SkipSmokeTest
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo
# Developers build from the pinned local virtual environment.  GitHub Actions
# supplies Python through actions/setup-python instead, so do not require a
# .venv there.
$venvPython = Join-Path $repo ".venv\Scripts\python.exe"
$python = if (Test-Path $venvPython) { $venvPython } else { "python" }

$migrationFiles = Get-ChildItem "$repo\migrations" -Filter "*.sql" -File
if ($migrationFiles.Count -eq 0) { throw "Tidak ada berkas migrasi SQL untuk dibundel." }
$pyInstallerArgs = @(
    "--noconfirm", "--clean", "--windowed", "--onedir", "--name", "DifferentNetworkTranscribe",
    "--icon", "$repo\assets\brand\dn-favicon.ico",
    "--specpath", "$repo\build\spec",
    "--collect-all", "numpy", "--collect-all", "faster_whisper", "--collect-all", "ctranslate2",
    "--collect-all", "av", "--collect-all", "PySide6"
)
$pyInstallerArgs += "--add-data"
$pyInstallerArgs += "$repo\assets;assets"
foreach ($migration in $migrationFiles) {
    # Add each SQL file explicitly. Passing the directory proved unreliable in
    # the frozen one-folder layout and resulted in an empty migrations folder.
    $pyInstallerArgs += "--add-data"
    $pyInstallerArgs += "$($migration.FullName);migrations"
}
$pyInstallerArgs += "app\main.py"
& $python -m PyInstaller @pyInstallerArgs
if ($LASTEXITCODE -ne 0) { throw "PyInstaller gagal" }

$isccCandidates = @(
    (Join-Path $env:LOCALAPPDATA "Programs\Inno Setup 6\ISCC.exe"),
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { $_ -and (Test-Path $_) }
$iscc = $isccCandidates | Select-Object -First 1
if ($null -eq $iscc) { throw "Inno Setup tidak ditemukan" }
& $iscc installer\different-network-transcribe.iss
if ($LASTEXITCODE -ne 0) { throw "Inno Setup gagal" }

New-Item -ItemType Directory -Force release | Out-Null
$version = & $python -c "from app.version import APP_VERSION; print(APP_VERSION)"
if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($version)) { throw "Versi aplikasi tidak dapat dibaca." }
$portableArtifact = "release\DifferentNetworkTranscribe-Portable-x64-v$version.zip"
Compress-Archive -Path dist\DifferentNetworkTranscribe\* -DestinationPath $portableArtifact -Force
$hashLines = @(
    Get-ChildItem release -File |
        Where-Object { $_.Name -ne "SHA256SUMS.txt" } |
        ForEach-Object {
            $artifact = $_
            $hash = (Get-FileHash -LiteralPath $artifact.FullName -Algorithm SHA256).Hash
            [System.String]::Format("{0}  {1}", $hash, $artifact.Name)
        }
)
$invalidHashLines = @($hashLines | Where-Object { $_ -notmatch '^[0-9A-F]{64}  \S+$' })
if ($hashLines.Count -eq 0 -or $invalidHashLines.Count -ne 0) {
    throw "Manifest SHA256SUMS tidak valid."
}
$hashLines | Set-Content release\SHA256SUMS.txt -Encoding utf8

if (-not $SkipSmokeTest) {
    & "$PSScriptRoot\smoke-test.ps1" -Artifact All
    if ($LASTEXITCODE -ne 0) { throw "Smoke test packaging gagal" }
}
