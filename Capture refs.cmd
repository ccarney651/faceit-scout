@echo off
cd /d "%~dp0"
set "OW=.venv\Scripts\owscout.exe"
if not exist "%OW%" (
  echo ERROR: %OW% not found. Install with:  .venv\Scripts\pip install -e .[capture]
  pause & exit /b 1
)
echo Reference-portrait capture. Get each hero on screen (practice range / replay)
echo at your calibrated resolution, then confirm. Captures alive + dead states.
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 refs capture %*
echo.
echo Verifying library...
"%OW%" --db owscout.sqlite3 --faceit-db faceit.sqlite3 refs verify
pause
