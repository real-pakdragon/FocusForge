<#
    Create the GitHub repository and push this project.
    Requires the GitHub CLI:  winget install --id GitHub.cli

    Usage:
        powershell -ExecutionPolicy Bypass -File .\publish.ps1
        powershell -ExecutionPolicy Bypass -File .\publish.ps1 -Repo my-name -Visibility private
#>
param(
    [string]$Repo = "FocusForge",
    [ValidateSet("public", "private")]
    [string]$Visibility = "public"
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
    Write-Host "GitHub CLI not found. Install it with:" -ForegroundColor Yellow
    Write-Host "    winget install --id GitHub.cli" -ForegroundColor Yellow
    Write-Host "then run this script again." -ForegroundColor Yellow
    exit 1
}

gh auth status *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Signing in to GitHub..." -ForegroundColor Cyan
    gh auth login
}

Write-Host "Creating $Visibility repository '$Repo' and pushing..." -ForegroundColor Cyan
gh repo create $Repo "--$Visibility" --source . --remote origin --push

if ($LASTEXITCODE -eq 0) {
    $url = gh repo view $Repo --json url -q .url
    Write-Host "Published: $url" -ForegroundColor Green
}
