@echo off
cd /d "%~dp0"
set "OW=.venv\Scripts\owscout.exe"
if not exist "%OW%" (
  echo ERROR: %OW% not found. Install with:  .venv\Scripts\pip install -e .[capture]
  pause & exit /b 1
)
echo Get Overwatch (or a replay) on screen at native resolution, then switch back.
echo Calibrating ROI/anchor boxes...
"%OW%" --db owscout.sqlite3 calibrate %*
pause
