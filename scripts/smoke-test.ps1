<#
.SYNOPSIS
  Smoke-tests the Windows installer and portable ZIP in temporary directories.

.DESCRIPTION
  Both artifacts launch their built-in --self-test with Python removed from PATH.
  The installer lane also proves uninstall removes only application files and
  leaves a separately selected user-data directory intact.
#>
[CmdletBinding()]
param(
    [ValidateSet("All", "Installer", "Portable")]
    [string]$Artifact = "All"
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
Set-Location $repo

function Start-DntProcess([string]$FileName, [string]$Arguments, [bool]$WithoutPython) {
    $info = [System.Diagnostics.ProcessStartInfo]::new()
    $info.FileName = $FileName
    $info.Arguments = $Arguments
    $info.UseShellExecute = $false
    if ($WithoutPython) {
        $info.EnvironmentVariables["PATH"] = (($env:PATH -split ";" | Where-Object { $_ -notmatch "Python" }) -join ";")
        $info.EnvironmentVariables.Remove("PYTHONHOME")
        $info.EnvironmentVariables.Remove("PYTHONPATH")
    }
    $process = [System.Diagnostics.Process]::Start($info)
    $process.WaitForExit()
    if ($process.ExitCode -ne 0) {
        throw "Process gagal ($($process.ExitCode)): $FileName"
    }
}

function Test-Portable {
    $root = Join-Path $env:TEMP ("dnt-portable-smoke-" + [guid]::NewGuid().ToString("N"))
    $data = Join-Path $root "UserData"
    New-Item -ItemType Directory -Path $root,$data -Force | Out-Null
    Expand-Archive -LiteralPath "release\DifferentNetworkTranscribe-Portable-x64.zip" -DestinationPath $root -Force
    $exe = Get-ChildItem -LiteralPath $root -Filter "DifferentNetworkTranscribe.exe" -Recurse | Select-Object -First 1
    if ($null -eq $exe) { throw "Portable ZIP tidak berisi executable." }
    Start-DntProcess $exe.FullName "--engine-import-self-test" $true
    Start-DntProcess $exe.FullName ('--data-dir "' + $data + '" --self-test') $true
    if ((Get-ChildItem -LiteralPath $data -Directory | Measure-Object).Count -lt 7) {
        throw "Portable build tidak membuat struktur data."
    }
    Write-Host "PASS portable ZIP" -ForegroundColor Green
}

function Test-Installer {
    $root = Join-Path $env:TEMP ("dnt-installer-smoke-" + [guid]::NewGuid().ToString("N"))
    $application = Join-Path $root "Application"
    $data = Join-Path $root "UserData"
    $log = Join-Path $root "setup.log"
    New-Item -ItemType Directory -Path $root,$data -Force | Out-Null
    $setup = (Resolve-Path "release\DifferentNetworkTranscribe-Setup-x64.exe").Path
    Start-DntProcess $setup ('/VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- /DIR="' + $application + '" /LOG="' + $log + '"') $false
    $exe = Join-Path $application "DifferentNetworkTranscribe.exe"
    if (-not (Test-Path -LiteralPath $exe) -or -not (Test-Path -LiteralPath $log)) {
        throw "Installer tidak menghasilkan executable atau log."
    }
    Start-DntProcess $exe "--engine-import-self-test" $true
    Start-DntProcess $exe ('--data-dir "' + $data + '" --self-test') $true
    $uninstaller = Join-Path $application "unins000.exe"
    if (-not (Test-Path -LiteralPath $uninstaller)) { throw "Uninstaller tidak ditemukan." }
    Start-DntProcess $uninstaller "/VERYSILENT /SUPPRESSMSGBOXES /NORESTART" $false
    if ((Test-Path -LiteralPath $exe) -or -not (Test-Path -LiteralPath $data)) {
        throw "Uninstall tidak membersihkan app atau menghapus data pengguna."
    }
    Write-Host "PASS installer" -ForegroundColor Green
}

if ($Artifact -in "All", "Portable") { Test-Portable }
if ($Artifact -in "All", "Installer") { Test-Installer }
