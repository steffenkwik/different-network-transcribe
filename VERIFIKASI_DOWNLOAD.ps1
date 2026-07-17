<#
.SYNOPSIS
Memeriksa checksum SHA-256 berkas unduhan terhadap SHA256SUMS.txt dari release.

.DESCRIPTION
Gunakan sebelum membuka installer EXE atau ZIP portable. Script hanya membaca
file dan manifest lokal; tidak mengunduh, mengubah, atau menjalankan aplikasi.
#>

[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$File,

    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$Manifest
)

$ErrorActionPreference = 'Stop'
$filePath = (Resolve-Path -LiteralPath $File).Path
$manifestPath = (Resolve-Path -LiteralPath $Manifest).Path
$fileName = [System.IO.Path]::GetFileName($filePath)
$line = Get-Content -LiteralPath $manifestPath | Where-Object {
    $_ -match ('^([A-Fa-f0-9]{64})\s{2}' + [regex]::Escape($fileName) + '$')
} | Select-Object -First 1

if ($null -eq $line) {
    throw "Checksum untuk '$fileName' tidak ditemukan di $manifestPath. Pastikan manifest berasal dari release yang sama."
}

$expected = ($line -split '\s+')[0].ToUpperInvariant()
$actual = (Get-FileHash -LiteralPath $filePath -Algorithm SHA256).Hash.ToUpperInvariant()

if ($actual -ne $expected) {
    Write-Error "TIDAK VALID: checksum tidak cocok. Jangan jalankan file; hapus dan unduh ulang dari GitHub Releases."
    exit 1
}

Write-Host "VALID: SHA-256 cocok untuk $fileName." -ForegroundColor Green
