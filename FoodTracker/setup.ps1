#requires -Version 5.1
<#
Install FoodShare Tracker dependencies without starting the app or changing data.
Run from PowerShell: powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1
Optional: -Python "C:\Path To Python\python.exe" or -RecreateVenv
#>
[CmdletBinding()]
param(
    [string]$Python,
    [switch]$RecreateVenv
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

function Get-PythonInfo {
    param([string]$Command, [string[]]$PrefixArguments = @())

    # Windows PowerShell can treat redirected native stderr as a terminating error.
    # An unavailable launcher version is expected; inspect its exit code instead.
    $ErrorActionPreference = "Continue"
    $PSNativeCommandUseErrorActionPreference = $false
    $probe = @'
import json, os, sys, sysconfig
supported = sys.version_info >= (3, 11) and os.name == 'nt' and sysconfig.get_platform().startswith('win')
if not supported:
    sys.exit(1)
print(json.dumps({'executable': sys.executable, 'version': sys.version.split()[0],
                 'prefix': sys.prefix, 'is_venv': sys.prefix != sys.base_prefix}))
'@
    try {
        $global:LASTEXITCODE = 1
        $outputLines = @(& $Command @PrefixArguments -c $probe 2>$null)
        if ($LASTEXITCODE -ne 0) { return $null }
        return ($outputLines -join "`n" | ConvertFrom-Json -ErrorAction Stop)
    }
    catch { return $null }
}

function Invoke-CheckedPython {
    param([string]$Command, [string[]]$Arguments, [string]$FailureMessage)

    $ErrorActionPreference = "Continue"
    $PSNativeCommandUseErrorActionPreference = $false
    $global:LASTEXITCODE = 1
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "$FailureMessage (exit code $LASTEXITCODE). See the output above."
    }
}

function Resolve-PythonCommand {
    param([string]$Name)

    if (Test-Path -LiteralPath $Name -PathType Leaf) {
        return (Get-Item -LiteralPath $Name).FullName
    }
    $found = Get-Command -Name $Name -CommandType Application -ErrorAction SilentlyContinue |
        Select-Object -First 1
    if ($found) { return $found.Source }
    return $null
}

$locationPushed = $false
try {
    if ($env:OS -ne "Windows_NT") {
        throw "This installer is for Windows. On macOS/Linux, follow README.md."
    }
    Push-Location -LiteralPath $PSScriptRoot
    $locationPushed = $true
    $requirements = Join-Path $PSScriptRoot "requirements.txt"
    $venvDirectory = Join-Path $PSScriptRoot ".venv"
    $venvPython = Join-Path $venvDirectory "Scripts\python.exe"
    if (-not (Test-Path -LiteralPath $requirements -PathType Leaf)) {
        throw "requirements.txt is missing. Put setup.ps1 in the FoodTracker folder."
    }

    $venvExists = Test-Path -LiteralPath $venvDirectory
    if ($venvExists -and -not $RecreateVenv) {
        if ($Python) {
            throw "An environment already exists. Use -RecreateVenv with -Python to replace it."
        }
        $info = Get-PythonInfo -Command $venvPython
        if (-not $info -or -not $info.is_venv -or
            [IO.Path]::GetFullPath($info.prefix) -ne [IO.Path]::GetFullPath($venvDirectory)) {
            throw "The existing .venv is unusable. Close apps using it, then rerun with -RecreateVenv. Nothing was deleted."
        }
        Write-Host "Reusing .venv (Python $($info.version))." -ForegroundColor Cyan
    }
    else {
        $candidates = @()
        if ($Python) {
            $candidates += @{ Command = $Python; Prefix = @() }
        }
        else {
            $candidates = @(
                @{ Command = "py.exe"; Prefix = @("-3") },
                @{ Command = "py.exe"; Prefix = @("-3.14") },
                @{ Command = "py.exe"; Prefix = @("-3.13") },
                @{ Command = "py.exe"; Prefix = @("-3.12") },
                @{ Command = "py.exe"; Prefix = @("-3.11") },
                @{ Command = "python.exe"; Prefix = @() },
                @{ Command = "python3.exe"; Prefix = @() }
            )
        }
        $selectedPython = $null
        foreach ($candidate in $candidates) {
            $commandPath = Resolve-PythonCommand -Name $candidate.Command
            if (-not $commandPath) { continue }
            $candidateInfo = Get-PythonInfo -Command $commandPath -PrefixArguments $candidate.Prefix
            # Use a base interpreter so recreating .venv cannot remove the installer interpreter.
            if ($candidateInfo -and -not $candidateInfo.is_venv) {
                $selectedPython = $candidateInfo.executable
                Write-Host "Using Python $($candidateInfo.version): $selectedPython" -ForegroundColor Cyan
                break
            }
        }
        if (-not $selectedPython) {
            throw "A standard Windows Python 3.11+ installation was not found. Run py -0p, install Python from https://www.python.org/downloads/windows/, or use -Python with its full path. Existing files were kept."
        }

        # Replacement is explicit, and starts only after a suitable interpreter is found.
        if ($venvExists) {
            $venvItem = Get-Item -LiteralPath $venvDirectory -Force
            if ($venvItem.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw ".venv is a link/junction. Remove that link manually before creating a local environment."
            }
            Remove-Item -LiteralPath $venvDirectory -Recurse -Force
        }
        Invoke-CheckedPython -Command $selectedPython -Arguments @("-m", "venv", $venvDirectory) `
            -FailureMessage "Could not create .venv"
        $info = Get-PythonInfo -Command $venvPython
        if (-not $info -or -not $info.is_venv -or
            [IO.Path]::GetFullPath($info.prefix) -ne [IO.Path]::GetFullPath($venvDirectory)) {
            throw "The new .venv could not be verified. Check the Python installation and folder permissions."
        }
    }

    Write-Host "Installing dependencies from requirements.txt..." -ForegroundColor Cyan
    Invoke-CheckedPython -Command $venvPython -Arguments @("-m", "ensurepip", "--upgrade") `
        -FailureMessage "Could not prepare pip"
    Invoke-CheckedPython -Command $venvPython -Arguments @("-m", "pip", "install", "-r", $requirements) `
        -FailureMessage "Dependency installation failed"
    Invoke-CheckedPython -Command $venvPython -Arguments @("-m", "pip", "check") `
        -FailureMessage "Installed dependencies are inconsistent"
    Invoke-CheckedPython -Command $venvPython -Arguments @("-c", "import streamlit, pytest, tzdata; print('Streamlit:', streamlit.__version__); print('pytest:', pytest.__version__)") `
        -FailureMessage "Installed packages could not be imported"

    Write-Host ""
    Write-Host "Ready. Run these commands from $PSScriptRoot" -ForegroundColor Green
    Write-Host "  Tests:       .\.venv\Scripts\python.exe -m pytest"
    Write-Host "  Demo:        .\.venv\Scripts\python.exe run.py --demo"
    Write-Host "  First admin: .\.venv\Scripts\python.exe manage.py create-admin"
    Write-Host "  Normal mode: .\.venv\Scripts\python.exe run.py"
}
catch {
    Write-Host "Setup failed: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    if ($locationPushed) { Pop-Location }
}
