@echo off
cd /d "%~dp0"
set "APP=.venv\Scripts\owscout-app.exe"
if not exist "%APP%" (
  echo ERROR: %APP% not found. Install with:  .venv\Scripts\pip install -e .[capture]
  pause & exit /b 1
)
start "" "%APP%"
