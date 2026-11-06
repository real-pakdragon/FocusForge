<#
    Install FocusForge for the current user and create shortcuts.
    Usage:  powershell -ExecutionPolicy Bypass -File .\install.ps1
#>
param(
    [string]$Source = (Join-Path $PSScriptRoot "dist\FocusForge.exe"),
    [switch]$NoLaunch
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $Source)) {
    throw "Executable not found at $Source. Run .\build.ps1 first."
}

$installDir = Join-Path $env:LOCALAPPDATA "Programs\FocusForge"
$exe = Join-Path $installDir "FocusForge.exe"
New-Item -ItemType Directory -Force -Path $installDir | Out-Null
Copy-Item -LiteralPath $Source -Destination $exe -Force
Write-Host "Installed to $exe" -ForegroundColor Green

# ---- shortcuts -------------------------------------------------------------
$shell = New-Object -ComObject WScript.Shell
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
$targets = @(
    (Join-Path $desktop "FocusForge.lnk"),
    (Join-Path $startMenu "FocusForge.lnk")
)

foreach ($lnkPath in $targets) {
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath = $exe
    $lnk.WorkingDirectory = $installDir
    $lnk.IconLocation = "$exe,0"
    $lnk.Description = "FocusForge - Deep Work Challenge Timer"
    $lnk.Save()
    Write-Host "Shortcut: $lnkPath" -ForegroundColor Green
}

# ---- uninstaller -----------------------------------------------------------
$uninstall = Join-Path $installDir "Uninstall.ps1"
@'
$ErrorActionPreference = "SilentlyContinue"
$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$desktop = [Environment]::GetFolderPath("Desktop")
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
Remove-Item (Join-Path $desktop "FocusForge.lnk") -Force
Remove-Item (Join-Path $startMenu "FocusForge.lnk") -Force
Remove-Item "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FocusForge" -Recurse -Force
$data = Join-Path $env:APPDATA "FocusForge"
if (Test-Path $data) { Remove-Item $data -Recurse -Force }
Start-Process cmd -ArgumentList "/c timeout /t 1 >nul & rmdir /s /q `"$dir`"" -WindowStyle Hidden
'@ | Set-Content -LiteralPath $uninstall -Encoding UTF8

# ---- add/remove programs entry --------------------------------------------
$regPath = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\FocusForge"
New-Item -Path $regPath -Force | Out-Null
Set-ItemProperty $regPath -Name "DisplayName" -Value "FocusForge"
Set-ItemProperty $regPath -Name "DisplayVersion" -Value "1.0.0"
Set-ItemProperty $regPath -Name "Publisher" -Value "FocusForge"
Set-ItemProperty $regPath -Name "DisplayIcon" -Value "$exe,0"
Set-ItemProperty $regPath -Name "InstallLocation" -Value $installDir
Set-ItemProperty $regPath -Name "NoModify" -Value 1 -Type DWord
Set-ItemProperty $regPath -Name "NoRepair" -Value 1 -Type DWord
Set-ItemProperty $regPath -Name "UninstallString" -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstall`""

if (-not $NoLaunch) {
    Start-Process -FilePath $exe -WorkingDirectory $installDir
    Write-Host "FocusForge launched." -ForegroundColor Cyan
}

Write-Host ""
Write-Host "Done. A shortcut is on your desktop and in the Start Menu." -ForegroundColor Green
