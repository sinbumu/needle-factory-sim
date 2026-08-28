# Builds the Windows onedir bundle and the Inno Setup installer.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
# Output: dist/NeedleFactorySim/            (onedir bundle)
#         dist/NeedleFactorySim-Setup-<ver>.exe
#
# Requires: uv (deps incl. dev group), Inno Setup 6 (ISCC.exe on PATH or default dir).

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "=== 1/3 uv sync (with dev group) ==="
uv sync

Write-Host "=== 2/3 PyInstaller onedir build ==="
uv run pyinstaller packaging/NeedleFactorySim.spec --noconfirm --distpath dist --workpath build

Write-Host "=== 3/3 Inno Setup compile ==="
$iscc = (Get-Command ISCC.exe -ErrorAction SilentlyContinue).Source
if (-not $iscc) {
    $candidates = @(
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe",
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}
if (-not $iscc) {
    Write-Error "ISCC.exe not found. Install Inno Setup 6: winget install -e --id JRSoftware.InnoSetup"
}
& $iscc packaging\installer.iss

Write-Host "Done. Installer is in dist\"
