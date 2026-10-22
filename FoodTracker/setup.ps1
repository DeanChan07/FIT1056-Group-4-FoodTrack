# FoodShare Tracker setup for Windows PowerShell.
# Builds a fresh .venv with Python 3.11 or newer, installs the pinned dependencies.
#   Run from this folder:  .\setup.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$pythonCommand = $null
$pythonPrefix = @()
foreach ($candidate in @(
    @{ Command = "py"; Prefix = @("-3.13") },
    @{ Command = "py"; Prefix = @("-3.12") },
    @{ Command = "py"; Prefix = @("-3.11") },
    @{ Command = "py"; Prefix = @("-3") },
    @{ Command = "python"; Prefix = @() }
)) {
    if (-not (Get-Command $candidate.Command -ErrorAction SilentlyContinue)) { continue }
    $prefixArgs = @($candidate.Prefix)
    & $candidate.Command @prefixArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $pythonCommand = $candidate.Command
        $pythonPrefix = $prefixArgs
        break
    }
}
if (-not $pythonCommand) {
    Write-Host "Python 3.11 or newer was not found." -ForegroundColor Red
    Write-Host "Install it from https://www.python.org/downloads/ and tick 'Add python.exe to PATH', then run this again."
    exit 1
}

Write-Host "Using $pythonCommand $pythonPrefix" -ForegroundColor Cyan
if (Test-Path ".venv") { Remove-Item -Recurse -Force ".venv" }
& $pythonCommand @pythonPrefix -m venv .venv
if ($LASTEXITCODE -ne 0) { throw "Could not create .venv." }
& .\.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not update pip." }
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt --quiet
if ($LASTEXITCODE -ne 0) { throw "Could not install requirements." }

Write-Host ""
Write-Host "Ready." -ForegroundColor Green
Write-Host "  Start the app:  .\.venv\Scripts\python.exe run.py      (opens http://localhost:8501)"
Write-Host "  Run the tests:  .\.venv\Scripts\python.exe -m pytest"
Write-Host "  First admin:    .\.venv\Scripts\python.exe manage.py create-admin"
Write-Host "  Classroom demo: .\.venv\Scripts\python.exe run.py --demo"
