@echo off
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv\Scripts\python.exe" set "PY=.venv\Scripts\python.exe"
if not defined PY (
  py -3 -V >nul 2>nul
  if not errorlevel 1 set "PY=py -3"
)
if not defined PY (
  python -V >nul 2>nul
  if not errorlevel 1 set "PY=python"
)
if not defined PY (
  echo [sotto] Python 3.10+ was not found on PATH.
  echo [sotto] Install Python, or create a venv and try again.
  exit /b 1
)

%PY% -c "import faster_whisper" >nul 2>nul
if errorlevel 1 (
  echo [sotto] Installing the transcription engine ^(first run only^)...
  %PY% -m pip install -r requirements.txt
  if errorlevel 1 (
    echo [sotto] Dependency install failed. See README.md.
    exit /b 1
  )
)

%PY% -m sotto_notes %*
