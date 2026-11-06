<#
    Build FocusForge into a single self-contained Windows executable.
    Usage:  powershell -ExecutionPolicy Bypass -File .\build.ps1
#>
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "==> Generating icon" -ForegroundColor Cyan
python tools\make_icon.py

Write-Host "==> Running smoke test" -ForegroundColor Cyan
python tests\smoke_test.py
if ($LASTEXITCODE -ne 0) { throw "Smoke test failed." }

Write-Host "==> Building executable" -ForegroundColor Cyan
python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --windowed `
    --name FocusForge `
    --icon assets\icon.ico `
    --add-data "assets\icon.ico;assets" `
    --version-file assets\version_info.txt `
    src\app.py

if (-not (Test-Path "dist\FocusForge.exe")) { throw "Build did not produce dist\FocusForge.exe" }

$size = [math]::Round((Get-Item "dist\FocusForge.exe").Length / 1MB, 1)
Write-Host "==> Built dist\FocusForge.exe ($size MB)" -ForegroundColor Green
