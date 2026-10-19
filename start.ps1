# Fuelora: set up on first run, fetch the latest prices, start the server, and open the page.
# Usage (Windows PowerShell):  .\start.ps1
# If Windows blocks the script:  powershell -ExecutionPolicy Bypass -File .\start.ps1
Set-Location -Path $PSScriptRoot

function Test-Python {
    param([string]$Exe, [string[]]$Prefix)
    try {
        & $Exe @Prefix -c "import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

$pyExe = $null
$pyPrefix = @()
foreach ($candidate in @(@("py", "-3"), @("python"), @("python3"))) {
    $exe = $candidate[0]
    $prefix = @($candidate | Select-Object -Skip 1)
    if ((Get-Command $exe -ErrorAction SilentlyContinue) -and (Test-Python $exe $prefix)) {
        $pyExe = $exe
        $pyPrefix = $prefix
        break
    }
}
if (-not $pyExe) {
    Write-Host "Python 3.10 or newer is required. Install it from https://www.python.org/downloads/" -ForegroundColor Red
    exit 1
}

$venvPy = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-Host "First run: setting up a private Python environment in .venv ..."
    & $pyExe @pyPrefix -m venv .venv
    if ($LASTEXITCODE -ne 0) { Write-Host "Could not create .venv." -ForegroundColor Red; exit 1 }
}

& $venvPy -m pip install --quiet -r requirements.txt
if ($LASTEXITCODE -ne 0) { Write-Host "Could not install requirements." -ForegroundColor Red; exit 1 }

Write-Host "Fetching the latest prices ..."
& $venvPy app\server.py --fetch-only
if ($LASTEXITCODE -ne 0) {
    Write-Host "Warning: the fetch failed. Showing the last saved prices instead." -ForegroundColor Yellow
}

$url = "http://127.0.0.1:8000"
Start-Job -ScriptBlock { param($u) Start-Sleep -Seconds 2; Start-Process $u } -ArgumentList $url | Out-Null

& $venvPy app\server.py
