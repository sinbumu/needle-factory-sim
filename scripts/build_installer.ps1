# Builds the Windows onedir bundle and the Inno Setup installer.
#
# Usage:  powershell -ExecutionPolicy Bypass -File scripts/build_installer.ps1
# Output: dist/NeedleFactorySim/            (onedir bundle)
#         dist/NeedleFactorySim-Setup-<ver>.exe
#
# Requires: uv (deps incl. dev group), Inno Setup 6 (ISCC.exe on PATH or default dir).

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

Write-Host "=== 1/4 uv sync (with dev group) ==="
uv sync

Write-Host "=== 2/4 PyInstaller onedir build ==="
uv run pyinstaller packaging/NeedleFactorySim.spec --noconfirm --distpath dist --workpath build

Write-Host "=== 3/4 Verifying the packaged build ==="
# A module reached only through a computed import is silently dropped by
# PyInstaller. That shipped once and made every provider-touching button dead,
# so the build now fails here instead of at the user.
$report = Join-Path $env:TEMP "nfs-selfcheck.txt"
if (Test-Path $report) { Remove-Item $report }
$exe = Join-Path (Get-Location) "dist\NeedleFactorySim\NeedleFactorySim.exe"
$proc = Start-Process $exe -ArgumentList "--selfcheck", $report -PassThru -Wait
if (Test-Path $report) { Get-Content $report }
if ($proc.ExitCode -ne 0) {
    Write-Error "Packaged build self-check FAILED - see the report above. Not building an installer."
}

Write-Host "=== 4/4 Inno Setup compile ==="
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
