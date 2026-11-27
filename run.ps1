# sotto-notes launcher for PowerShell 5.1 / 7+
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$python = $null
$pyArgs = @()
if (Test-Path ".venv\Scripts\python.exe") {
    $python = ".venv\Scripts\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
    $pyArgs = @("-3")
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = "python"
}

if (-not $python) {
    Write-Host "[sotto] Python 3.10+ was not found on PATH." -ForegroundColor Red
    Write-Host "[sotto] Install Python, or create a venv and try again."
    exit 1
}

& $python @pyArgs -c "import faster_whisper" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "[sotto] Installing the transcription engine (first run only)..." -ForegroundColor Yellow
    & $python @pyArgs -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[sotto] Dependency install failed. See README.md." -ForegroundColor Red
        exit 1
    }
}

& $python @pyArgs -m sotto_notes @args
