# FoodShare Tracker setup for Windows PowerShell.
# Builds a fresh .venv with Python 3.11 or newer, installs Streamlit and makes demo data.
#   Run from this folder:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
foreach ($candidate in @("py -3.13", "py -3.12", "py -3.11", "py -3", "python")) {
    $parts = $candidate.Split(" ")
    if (-not (Get-Command $parts[0] -ErrorAction SilentlyContinue)) { continue }
    & $parts[0] $parts[1..($parts.Length - 1)] -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) { $python = $candidate; break }
}
if (-not $python) {
    Write-Host "Python 3.11 or newer was not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH', then run this again."
    exit 1
}

Write-Host "Using $python" -ForegroundColor Cyan
if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
Invoke-Expression "$python -m venv .venv"
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if (-not (Test-Path "data\foodshare.sqlite3")) { & .\.venv\Scripts\python.exe seed.py }

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host "  Start the app:  .\.venv\Scripts\python.exe run.py      (opens http://localhost:8501)"
Write-Host "  Run the tests:  .\.venv\Scripts\python.exe -m pytest"
Write-Host "  Demo sign-ins:  staff / recipient / volunteer / manager / admin"
Write-Host "  Demo password:  DemoPassword123!"
